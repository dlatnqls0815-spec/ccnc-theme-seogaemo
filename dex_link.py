"""Relocate the audited ccNC theme DEX and check its link with the adapter."""

from dataclasses import dataclass
from hashlib import sha1, sha256
import re
from struct import Struct, pack_into, unpack_from
from zlib import adler32


DEX_MAGIC = b"dex\n035\0"
THEME_SHA256 = "542e2c2ed16ce270fe7f6d5efb1c4840b76f884cb8fada6532cd152afcb6eb6e"
THEME_ENTRY = "Ldev/ev6/nowplaying/UniversalEntry;"
HOST_PREFIX = "Lhmgapi/hook/"
ADAPTER_PREFIX = "Lgl3ccnc/api/"
DESCRIPTORS = {
    f"{HOST_PREFIX}{name};": f"{ADAPTER_PREFIX}{name};"
    for name in ("Bridge", "LoadedApp", "MethodHook$Param", "MethodHook", "ModContext", "ModEntry")
}
OPTIONAL_INPUT_LITERALS = {"hmgapi.hook.Input", "hmgapi.hook.Input$Binding"}
HEADER_SIZE = 112
NO_INDEX = 0xFFFFFFFF
PUBLIC = 0x0001
PROTECTED = 0x0004
STATIC = 0x0008
ABSTRACT = 0x0400
METHOD_LABEL = re.compile(rb"^\s*[0-9a-f]+:\s+\|\[[0-9a-f]+\] (.*)$")
INSTRUCTION = re.compile(rb"^\s*([0-9a-f]+): [0-9a-f. ]+\|([0-9a-f]+): (.*)$")
ID_COMMENT = re.compile(rb" // (?:method|field|string|type)@[0-9a-f]+$")
PAYLOAD = re.compile(rb"^(?:packed-switch|sparse-switch|array)-data \(([0-9]+) units\)$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"DEX: {message}")


def unsigned_leb(data: bytes, offset: int) -> tuple[int, int]:
    number = 0
    for shift in range(0, 35, 7):
        require(offset < len(data), "truncated ULEB128")
        byte = data[offset]
        offset += 1
        number |= (byte & 0x7F) << shift
        if byte < 0x80:
            require(number <= NO_INDEX, "ULEB128 overflow")
            return number, offset
    raise ValueError("DEX: invalid ULEB128 continuation")


def strictly_ordered(items) -> bool:
    return all(first < second for first, second in zip(items, items[1:]))


@dataclass
class Definition:
    flags: int
    superclass: str | None
    interfaces: tuple[str, ...]
    fields: dict
    methods: dict


class Dex:
    def __init__(self, data: bytes):
        require(len(data) >= HEADER_SIZE and data[:8] == DEX_MAGIC, "expected DEX version 035")
        require(data[12:32] == sha1(data[32:]).digest(), "SHA-1 signature mismatch")
        require(unpack_from("<I", data, 8)[0] == adler32(data[12:]), "Adler-32 mismatch")
        size, header, endian, link_size, link_off, map_off = unpack_from("<6I", data, 32)
        require(size == len(data) and header == HEADER_SIZE and endian == 0x12345678, "bad header")
        require(link_size == link_off == 0, "unexpected link data")
        self.data = data
        self.data_size, self.data_off = unpack_from("<2I", data, 104)
        require(self.data_off % 4 == 0 and self.data_off + self.data_size == size, "bad data range")

        header_tables = unpack_from("<12I", data, 56)
        tables = list(zip(header_tables[::2], header_tables[1::2]))
        self.map = self.read_map(map_off)
        require(self.map.get(0) == (1, 0) and self.map.get(0x1000) == (1, map_off), "bad map records")
        previous_end = HEADER_SIZE
        for kind, ((count, offset), width) in enumerate(zip(tables, (4, 4, 12, 8, 8, 32)), 1):
            require(self.map.get(kind, (0, 0)) == (count, offset), "map and ID table disagree")
            if count:
                end = offset + count * width
                require(previous_end <= offset and offset % 4 == 0 and end <= self.data_off, "bad ID table range")
                previous_end = end

        string_count, _ = tables[0]
        require(self.map.get(0x2002, (0, 0))[0] == string_count, "map and string data count disagree")
        self.string_offsets = tuple(row[0] for row in self.rows(tables[0], "<I"))
        string_rows = [self.read_string(offset) for offset in self.string_offsets]
        self.strings = tuple(value for value, _ in string_rows)
        self.string_payload_offsets = tuple(offset for _, offset in string_rows)
        require(len(set(self.string_offsets)) == string_count, "duplicate string data offset")
        require(strictly_ordered([value.encode("utf-16-be", "surrogatepass") for value in self.strings]),
                "unordered or duplicate string IDs")

        type_ids = [row[0] for row in self.rows(tables[1], "<I")]
        require(strictly_ordered(type_ids), "unordered or duplicate type IDs")
        self.types = tuple(self.item(self.strings, index) for index in type_ids)

        proto_rows = [(shorty, result, self.type_ids_at(parameters))
                      for shorty, result, parameters in self.rows(tables[2], "<3I")]
        require(strictly_ordered([(result, parameters) for _, result, parameters in proto_rows]),
                "unordered or duplicate proto IDs")
        self.protos = tuple(self.proto(shorty, result, parameters) for shorty, result, parameters in proto_rows)

        field_rows = list(self.rows(tables[3], "<2HI"))
        require(strictly_ordered([(owner, name, value_type) for owner, value_type, name in field_rows]),
                "unordered or duplicate field IDs")
        self.fields = tuple((self.item(self.types, owner), self.item(self.strings, name), self.item(self.types, value_type))
                            for owner, value_type, name in field_rows)

        method_rows = list(self.rows(tables[4], "<2HI"))
        require(strictly_ordered([(owner, name, proto) for owner, proto, name in method_rows]),
                "unordered or duplicate method IDs")
        self.methods = tuple((self.item(self.types, owner), self.item(self.strings, name), self.item(self.protos, proto))
                             for owner, proto, name in method_rows)

        self.classes = {}
        for class_idx, flags, superclass, interfaces, source, annotations, class_data, values in self.rows(tables[5], "<8I"):
            descriptor = self.item(self.types, class_idx)
            require(descriptor.startswith("L") and descriptor.endswith(";") and descriptor not in self.classes,
                    f"invalid or duplicate class definition {descriptor}")
            parent = None if superclass == NO_INDEX else self.item(self.types, superclass)
            implements = tuple(self.item(self.types, index) for index in self.type_ids_at(interfaces))
            if source != NO_INDEX:
                self.item(self.strings, source)
            for kind, offset in ((0x2006, annotations), (0x2005, values)):
                if offset:
                    self.section_range(kind, offset, 1)
            fields, methods = self.class_data(descriptor, class_data)
            self.classes[descriptor] = Definition(flags, parent, implements, fields, methods)

    def read_map(self, offset: int) -> dict:
        require(self.data_off <= offset <= len(self.data) - 4 and offset % 4 == 0, "bad map offset")
        count = unpack_from("<I", self.data, offset)[0]
        require(0 < count <= (len(self.data) - offset - 4) // 12, "bad map size")
        records = list(self.rows((count, offset + 4), "<2H2I"))
        require(strictly_ordered([start for _, _, _, start in records]), "unordered map offsets")
        result = {}
        for kind, unused, length, start in records:
            require(unused == 0 and length > 0 and kind not in result and start < len(self.data), "invalid map item")
            require(kind < 0x1000 or start >= self.data_off, "data section outside data range")
            result[kind] = (length, start)
        self.map_ends = {kind: records[index + 1][3] if index + 1 < count else len(self.data)
                         for index, (kind, _, _, _) in enumerate(records)}
        require(offset + 4 + 12 * count <= self.map_ends.get(0x1000, 0), "map list overlaps another section")
        return result

    def rows(self, table: tuple[int, int], form: str):
        count, offset = table
        row = Struct(form)
        for index in range(count):
            yield row.unpack_from(self.data, offset + row.size * index)

    def section_range(self, kind: int, offset: int, size: int) -> int:
        start = self.map.get(kind, (0, 0))[1]
        end = self.map_ends.get(kind, 0)
        require(start <= offset < end and size <= end - offset, f"offset outside map section 0x{kind:04x}")
        return end

    @staticmethod
    def item(table: tuple, index: int):
        require(index < len(table), "index outside ID table")
        return table[index]

    def read_string(self, offset: int) -> tuple[str, int]:
        end = self.section_range(0x2002, offset, 1)
        utf16_length, payload_offset = unsigned_leb(self.data, offset)
        terminator = self.data.find(b"\0", payload_offset, end)
        require(terminator != -1, "unterminated string")
        raw = self.data[payload_offset:terminator].replace(b"\xC0\x80", b"\0")
        require(not any(byte >= 0xF0 for byte in raw), "invalid MUTF-8 encoding")
        result = raw.decode("utf-8", "surrogatepass")
        require(len(result) == utf16_length, "wrong MUTF-8 string length")
        return result, payload_offset

    def type_ids_at(self, offset: int) -> tuple[int, ...]:
        if not offset:
            return ()
        require(offset % 4 == 0, "misaligned type list")
        self.section_range(0x1001, offset, 4)
        count = unpack_from("<I", self.data, offset)[0]
        self.section_range(0x1001, offset, 4 + 2 * count)
        return unpack_from(f"<{count}H", self.data, offset + 4)

    def proto(self, shorty: int, result: int, parameters: tuple[int, ...]) -> str:
        return_type = self.item(self.types, result)
        argument_types = [self.item(self.types, index) for index in parameters]
        short_form = "".join("L" if value.startswith("[") else value[0] for value in [return_type, *argument_types])
        require(self.item(self.strings, shorty) == short_form, "incorrect shorty descriptor")
        return "(" + "".join(argument_types) + ")" + return_type

    def class_data(self, descriptor: str, offset: int) -> tuple[dict, dict]:
        fields, methods = {}, {}
        if not offset:
            return fields, methods
        end = self.section_range(0x2000, offset, 1)
        counts = []
        for _ in range(4):
            count, offset = unsigned_leb(self.data, offset)
            counts.append(count)
        tables = ((self.fields, fields), (self.fields, fields), (self.methods, methods), (self.methods, methods))
        for kind, (count, (table, definitions)) in enumerate(zip(counts, tables)):
            require(count <= len(table), "class data count outside ID table")
            index = 0
            for _ in range(count):
                difference, offset = unsigned_leb(self.data, offset)
                access, offset = unsigned_leb(self.data, offset)
                index += difference
                member = self.item(table, index)
                require(member[0] == descriptor and member not in definitions, "invalid class member ID")
                if kind < 2:
                    definitions[member] = access
                    continue
                code_off, offset = unsigned_leb(self.data, offset)
                if code_off:
                    require(code_off % 4 == 0, "misaligned code item")
                    self.section_range(0x2001, code_off, 16)
                    insns_count = unpack_from("<I", self.data, code_off + 12)[0]
                    self.section_range(0x2001, code_off, 16 + insns_count * 2)
                definitions[member] = (access, bool(code_off))
        require(offset <= end, "class data overlaps another section")
        return fields, methods


def relocate_theme_dex(original: bytes) -> bytes:
    """Change just six fixed-width type strings so all DEX index numbers stay intact."""
    require(sha256(original).hexdigest() == THEME_SHA256, "input differs from audited ccNC Theme 0.1.31")
    old = Dex(original)
    old_hook_types = {value for value in old.types if HOST_PREFIX in value}
    require(old_hook_types == DESCRIPTORS.keys(), "upstream hook type set changed")

    patched = bytearray(original)
    for before, after in DESCRIPTORS.items():
        require(len(before) == len(after), "descriptor replacement changes size")
        index = old.strings.index(before)
        offset = old.string_payload_offsets[index]
        patched[offset:offset + len(before)] = after.encode("ascii")
    patched[12:32] = sha1(patched[32:]).digest()
    pack_into("<I", patched, 8, adler32(patched[12:]))

    relocated = bytes(patched)
    new = Dex(relocated)
    require(new.strings == tuple(DESCRIPTORS.get(value, value) for value in old.strings), "unexpected string change")
    require(new.types == tuple(DESCRIPTORS.get(value, value) for value in old.types), "unexpected type change")
    return relocated


def resolve_reference(classes: dict, table: str, reference: tuple):
    """Resolve this class/superclass ABI, which declares no interface members."""
    owner, *signature = reference
    visited = set()
    while owner in classes:
        require(owner not in visited, "cyclic superclass graph")
        visited.add(owner)
        definition = classes[owner]
        members = getattr(definition, table)
        member = (owner, *signature)
        if member in members:
            return members[member]
        owner = definition.superclass
    return None


def instruction_listing(dex: bytes, disassembly: bytes) -> dict:
    """Keep dexdump's symbolic operands, code-relative offsets and catch table."""
    methods = {}
    catch_tables = set()
    body = None
    reading_catches = False
    for line in disassembly.splitlines():
        label = METHOD_LABEL.match(line)
        if label:
            method = label[1]
            require(method not in methods, f"duplicate method in dexdump: {method!r}")
            body = []
            methods[method] = body
            reading_catches = False
        elif body is not None:
            operation = INSTRUCTION.match(line)
            value = line.strip()
            if operation:
                offset = int(operation[1], 16)
                address = int(operation[2], 16)
                instruction = ID_COMMENT.sub(b"", operation[3])
                payload = PAYLOAD.fullmatch(instruction)
                payload_bytes = b""
                if payload:
                    end = offset + 2 * int(payload[1])
                    require(end <= len(dex), "instruction payload outside DEX")
                    payload_bytes = dex[offset:end]
                body.append((address, instruction, payload_bytes))
            elif value.startswith(b"catches "):
                reading_catches = True
                catch_tables.add(method)
            elif value.startswith(b"positions "):
                reading_catches = False
            if reading_catches:
                body.append(value)
    require(catch_tables == methods.keys(), "incomplete dexdump catch tables")
    return methods


def verify_linked_dex(
    original: bytes,
    linked: bytes,
    entry_class: str,
    host_dex: bytes | None = None,
    *,
    disassembly: tuple[bytes, bytes] | None = None,
) -> dict:
    """Verify DEX ID order, original declarations and linkage to the two hook APIs."""
    relocated = relocate_theme_dex(original)
    theme = Dex(relocated)
    result = Dex(linked)
    require(THEME_ENTRY in theme.classes, "upstream entry missing")
    require(theme.classes[THEME_ENTRY].superclass == f"{ADAPTER_PREFIX}ModEntry;", "upstream entry mislinked")
    for name, definition in theme.classes.items():
        require(result.classes.get(name) == definition, f"changed theme declaration {name}")

    entry = "L" + entry_class.replace(".", "/") + ";"
    definition = result.classes.get(entry)
    require(definition is not None and definition.superclass == f"{HOST_PREFIX}ModEntry;", "entry must extend host ModEntry")
    require(definition.flags & PUBLIC and not definition.flags & ABSTRACT, "entry must be public and concrete")
    require(definition.methods.get((entry, "<init>", "()V")) == (0x10000 | PUBLIC, True), "entry requires public no-arg constructor")
    require(not any(name.startswith(HOST_PREFIX) for name in result.classes), "host API classes were bundled")
    adapter_types = {value.lstrip("[") for value in result.types if value.lstrip("[").startswith(ADAPTER_PREFIX)}
    require(set(DESCRIPTORS.values()) <= adapter_types <= result.classes.keys(), "missing relocated adapter class")
    require(all(result.classes[value].flags & PUBLIC for value in DESCRIPTORS.values()), "adapter class is not public")

    references = (("fields", result.fields), ("methods", result.methods))
    host_types = {value.lstrip("[") for value in result.types if value.lstrip("[").startswith(HOST_PREFIX)}
    host_classes = Dex(host_dex).classes if host_dex is not None else None
    if host_classes is not None:
        require(host_types <= host_classes.keys(), f"unknown host types: {sorted(host_types - host_classes.keys())}")
        require(all(host_classes[value].flags & PUBLIC for value in host_types), "host API class is not public")
    host_references = 0
    for table, members in references:
        for member in members:
            if member[0].startswith(ADAPTER_PREFIX):
                require(resolve_reference(result.classes, table, member) is not None, f"unresolved adapter {table}: {member}")
            if host_classes is not None and member[0].startswith(HOST_PREFIX):
                target = resolve_reference(host_classes, table, member)
                flags = target[0] if table == "methods" and target is not None else target
                require(flags is not None and flags & (PUBLIC | PROTECTED), f"unresolved host {table}: {member}")
                host_references += 1

    bridge_method = (f"{ADAPTER_PREFIX}Bridge;", "hookMethod", f"(Ljava/lang/reflect/Member;{ADAPTER_PREFIX}MethodHook;)V")
    flags, has_code = result.classes[bridge_method[0]].methods.get(bridge_method, (0, False))
    require((flags & (PUBLIC | STATIC)) == (PUBLIC | STATIC) and has_code,
            "adapter bridge requires a public static method")

    # DEX uses an inherited call whose method ID names NavigationHooks, not ModEntry.
    settings_method = (f"{ADAPTER_PREFIX}ModEntry;", "onSettingsChanged", f"({ADAPTER_PREFIX}ModContext;)V")
    target = result.classes[settings_method[0]].methods.get(settings_method)
    require(target is not None and target[0] & PUBLIC and target[1], "missing inherited onSettingsChanged method")
    require(OPTIONAL_INPUT_LITERALS <= set(result.strings), "upstream optional Input probe was changed")
    code_methods_checked = 0
    if disassembly is not None:
        theme_listing = instruction_listing(relocated, disassembly[0])
        result_listing = instruction_listing(linked, disassembly[1])
        theme_code_count = sum(has_code for cls in theme.classes.values() for _, has_code in cls.methods.values())
        result_code_count = sum(has_code for cls in result.classes.values() for _, has_code in cls.methods.values())
        require(len(theme_listing) == theme_code_count and len(result_listing) == result_code_count, "incomplete dexdump listings")
        for name, body in theme_listing.items():
            require(result_listing.get(name) == body, f"changed theme method body: {name!r}")
        code_methods_checked = len(theme_listing)
    return {
        "dex_version": "035",
        "theme_classes": len(theme.classes),
        "theme_methods": sum(len(definition.methods) for definition in theme.classes.values()),
        "linked_classes": len(result.classes),
        "host_references_checked": host_references,
        "theme_code_methods_checked": code_methods_checked,
    }
