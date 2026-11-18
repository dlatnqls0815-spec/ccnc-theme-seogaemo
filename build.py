#!/usr/bin/env python3
"""Build or verify the ccnc-theme-5w Seogaemo HSM offline (run tools/fetch_upstream.py first)."""

import argparse
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

sys.dont_write_bytecode = True

from dex_link import relocate_theme_dex, verify_linked_dex
from hsm_package import build_hsm, verify_hsm


OUT = Path(__file__).resolve().parent
UPSTREAM = OUT / "upstream"
HOST = UPSTREAM / "hmg-seogaemo"
THEME = UPSTREAM / "ccnc-theme-0.1.31" / "hooks.jar"
THEME_SHA256 = "3da93a80042227092d86f31d7cd9299c328eb8e2de80cc7ede71449384d8e28c"
MODULE = OUT / "module" / "ccnc-theme-5w"
DIST = OUT / "dist"
ENTRY = "gl3ccnc.host.ThemeEntry"
BUILD_TOOLS = "34.0.0"


def default_jdk():
    import os
    known_paths = []
    if os.environ.get("JAVA_HOME"):
        known_paths.append(Path(os.environ["JAVA_HOME"]))
    binary = shutil.which("javac")
    if binary:
        known_paths.append(Path(binary).resolve().parent.parent)
    known_paths.append(Path("jdk-17"))
    return next((p for p in known_paths if (p / "bin" / exe("javac")).is_file()), known_paths[0])


def default_sdk():
    import os
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(key):
            return Path(os.environ[key])
    return Path.home() / ".local/share/android-sdk"


def exe(name):
    return name + (".exe" if sys.platform == "win32" else "")


def require_file(path):
    if not path.is_file():
        raise ValueError(f"Missing build input: {path}")
    return path


def write_jar(path, members):
    with ZipFile(path, "w", allowZip64=False) as jar:
        for name, data in members:
            info = ZipInfo(name)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            jar.writestr(info, data)


def class_jar(path, classes):
    write_jar(path, ((p.relative_to(classes).as_posix(), p.read_bytes())
                     for p in sorted(classes.rglob("*.class"))))


class Toolchain:
    def __init__(self, jdk, sdk, work):
        self.java = require_file(jdk / "bin" / exe("java"))
        self.javac = require_file(jdk / "bin" / exe("javac"))
        tools = sdk / "build-tools" / BUILD_TOOLS
        self.d8_jar = require_file(tools / "lib" / "d8.jar")
        self.dexdump = require_file(tools / exe("dexdump"))
        sdk_jar = require_file(sdk / "platforms" / "android-35" / "android.jar")
        self.android = work / "android.jar"
        # javac's ZipFS needs the jar on a writable path under the Windows workspace sandbox.
        shutil.copyfile(sdk_jar, self.android)
        self.work = work

    def compile(self, sources, output, classpath=None):
        output.mkdir()
        args = [self.javac, f"-J-Djava.io.tmpdir={self.work}", "-encoding", "UTF-8",
                "-source", "7", "-target", "7", "-Xlint:-options",
                "-bootclasspath", self.android, "-d", output]
        if classpath is not None:
            args.extend(("-classpath", classpath))
        subprocess.run([*args, *sources], cwd=self.work, check=True)

    def dex(self, inputs, output, classpath=None):
        output.mkdir()
        args = [self.java, f"-Djava.io.tmpdir={self.work}", "-cp", self.d8_jar,
                "com.android.tools.r8.D8", "--release", "--min-api", "19",
                "--lib", self.android, "--output", output]
        if classpath is not None:
            args.extend(("--classpath", classpath))
        subprocess.run([*args, *inputs], cwd=self.work, check=True)
        if sorted(p.name for p in output.iterdir()) != ["classes.dex"]:
            raise ValueError("Expected a single classes.dex for the Gen5W DexClassLoader")
        return output / "classes.dex"

    def dump_dex(self, path):
        return subprocess.check_output([self.dexdump, "-d", path.name], cwd=path.parent)


def build_host_api(tools):
    if (HOST / "VERSION").read_text(encoding="utf-8").strip() != "0.1.54":
        raise ValueError("Expected HMG-Seogaemo source version 0.1.54")
    payload = HOST / "modules/wireless-carplay-and-aa/payload/src"
    sdk_src = tools.work / "host_src"
    for package in ("hmgapi/hook", "hmgapi/engine"):
        (sdk_src / package).mkdir(parents=True)
        for source in sorted((payload / package).glob("*.java.src")):
            (sdk_src / package / source.stem).write_bytes(source.read_bytes())
    for source in sorted((HOST / "core/hook/src/hmgapi/hook").glob("*.java")):
        (sdk_src / "hmgapi/hook" / source.name).write_bytes(source.read_bytes())

    classes = tools.work / "host_classes"
    tools.compile(sorted(sdk_src.rglob("*.java")), classes)
    host_api = tools.work / "host_api.jar"
    class_jar(host_api, classes)
    host_dex = tools.dex([host_api], tools.work / "host_dex")
    return host_api, host_dex.read_bytes()


def read_theme():
    jar_data = THEME.read_bytes()
    if hashlib.sha256(jar_data).hexdigest() != THEME_SHA256:
        raise ValueError("The input hooks.jar differs from the reviewed 0.1.31 artifact")
    with ZipFile(io.BytesIO(jar_data)) as jar:
        if jar.namelist() != ["classes.dex"]:
            raise ValueError("Expected the original hooks.jar to contain just classes.dex")
        return jar.read("classes.dex")


def verify_dex(tools, original, linked, host_dex):
    if not linked.startswith(b"dex\n035\0"):
        raise ValueError("The Gradle-free build must emit DEX 035 for Dalvik")
    before = tools.work / "relocated-for-check.dex"
    after = tools.work / "linked-for-check.dex"
    before.write_bytes(relocate_theme_dex(original))
    after.write_bytes(linked)
    return verify_linked_dex(original, linked, ENTRY, host_dex=host_dex,
                             disassembly=(tools.dump_dex(before), tools.dump_dex(after)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk", type=Path, default=default_jdk())
    parser.add_argument("--sdk", type=Path, default=default_sdk())
    parser.add_argument("--verify", type=Path, metavar="HSM", help="verify an existing HSM")
    parser.add_argument("--trusted-key", type=Path, help="verify using a separately pinned public PEM")
    args = parser.parse_args()
    if args.trusted_key and not args.verify:
        parser.error("--trusted-key requires --verify")

    state = OUT / ".build"
    state.mkdir(exist_ok=True)
    original = read_theme()
    with TemporaryDirectory(prefix="work-", dir=state) as temp:
        tools = Toolchain(args.jdk.resolve(), args.sdk.resolve(), Path(temp))
        host_api, host_dex = build_host_api(tools)
        if args.verify:
            path = args.verify.resolve()
            digest = verify_hsm(path, trusted_public_key=args.trusted_key)
            with ZipFile(path) as hsm:
                with ZipFile(io.BytesIO(hsm.read("files/ccnc-theme-hook.jar"))) as jar:
                    linked = jar.read("classes.dex")
            report = verify_dex(tools, original, linked, host_dex)
        else:
            classes = tools.work / "shim_classes"
            tools.compile(sorted((MODULE / "src").rglob("*.java")), classes, host_api)
            shim = tools.work / "shim.jar"
            class_jar(shim, classes)
            relocated = tools.work / "theme.dex"
            relocated.write_bytes(relocate_theme_dex(original))
            linked = tools.dex([shim, relocated], tools.work / "linked", host_api).read_bytes()
            report = verify_dex(tools, original, linked, host_dex)
            hook_jar = tools.work / "ccnc-theme-hook.jar"
            write_jar(hook_jar, [("classes.dex", linked)])
            path = build_hsm(MODULE, hook_jar, DIST, state / "local-signing-key.pem")
            digest = verify_hsm(path)
    print(f"HSM: {path}")
    print(f"SHA-256: {digest}")
    print("OK: HSM structure, integrity, signature, DEX 035 and hook ABI")
    print(f"DEX: {report['theme_classes']} theme classes, {report['theme_methods']} theme methods, "
          f"{report['theme_code_methods_checked']} theme method bodies and "
          f"{report['host_references_checked']} host API member references verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)
