# ccNC Theme 0.1.31과 서개모 0.1.54의 훅 API

테마 쪽은 제공된 `hooks.jar`의 `classes.dex`에서 타입, 메서드와 필드 참조를 읽었다. 서개모 쪽은 `VERSION`이 `0.1.54`인 제공 소스의 코어 빌드 구성을 재현해 Java API를 확인했다. 실제 차량에 설치된 바이너리와 차량 앱에서의 동작은 미확인이다.

## ABI 대조

아래 원본 타입은 모두 `hmgapi.hook`에 있다. 필드와 메서드의 타입은 실제 DEX 참조 기준이다.

| 테마가 요구하는 ABI | 서개모 0.1.54 코어에서 확인한 동작 | 이식 방식 |
| --- | --- | --- |
| `ModEntry.<init>()V`, `zygoteInit(ModContext)`, `appLoaded(ModContext, LoadedApp)` | 기본 생성자와 두 콜백을 제공한다. 코어는 부모 클래스 로더의 `ModEntry`를 상속한 공개 진입점을 생성한다. | `gl3ccnc.host.ThemeEntry`가 코어 콜백 두 개를 받아 원본 `UniversalEntry`에 전달한다. |
| `ModEntry.onEnabled(ModContext, boolean)`, `onSettingsChanged(ModContext)` | 메서드 선언은 있다. 코어 로더는 호출하지 않는다. | 원본의 상속 호출에 필요한 선언을 어댑터에 유지한다. 설정과 모듈 상태는 헤드유닛 재시작 후 반영된다. |
| `LoadedApp.classLoader:ClassLoader`, `context:Context`, `packageName:String` | 같은 공개 필드가 있고 코어가 대상 앱 바인딩 후 채운다. | 앱의 로더, 컨텍스트, 패키지명을 그대로 전달한다. |
| `MethodHook.<init>()V`, `beforeHookedMethod(Param)`, `afterHookedMethod(Param)` | 기본 생성자와 보호된 콜백 두 개를 제공한다. | 코어 훅의 각 콜백이 원본 콜백을 호출한다. |
| `MethodHook$Param.args:Object[]`, `thisObject:Object`, `setResult(Object)V`, `hasThrowable()Z` | 같은 공개 필드와 메서드를 제공한다. | 인자 배열과 객체를 공유하고 결과 설정과 예외 조회를 원래 코어 객체에 위임한다. |
| `Bridge.hookMethod(Member, MethodHook)V` | `public static synchronized void`로 제공한다. Dalvik에서 실제 `Method` 또는 `Constructor`의 훅을 설치한다. | 서개모 `Bridge`에 위임해 공용 호스트를 사용한다. |
| `ModContext.dir:File`, `log(String)V` | 같은 공개 필드와 메서드를 제공한다. `dir`은 설치된 모듈 디렉터리다. | 설치 디렉터리와 코어 로그를 사용한다. 원본이 선택적으로 읽는 `Pretendard-Bold.otf`는 제공 파일에 없어 폴백 경로를 따른다. |
| `ModContext.settingBoolean(String, boolean)Z` | 같은 메서드가 저장된 `on`/`true`와 호출자가 넘긴 기본값을 처리한다. | 서개모 설정 `progress_enabled`를 연결한다. 테마의 두 호출 모두 기본값이 `true`다. |
| `ModContext.setting(String)Object` | 이 시그니처는 없다. `settingString(String, String)String`을 제공한다. | 문자열 또는 `null`을 반환한다. 유일한 호출은 `bt_osd_mode`를 문자열로 취급한다. 0.1.31의 `OsdModePolicy.parse`는 항상 `HIDE_BT`를 반환하므로 이 키는 UI에 노출하지 않았다. |
| `ModContext.enabled()Z` | 이 메서드는 없다. 등록된 모듈을 자이고트 시작 시 로드한다. | 로드된 자이고트의 생명주기 동안 `true`를 반환한다. 끄고 재시작하면 등록이 빠진다. |
| 리플렉션 `hmgapi.hook.Input` / `Input$Binding` | 코어 구성에 두 클래스가 없다. | 입력 설정과 앱 설치 메타데이터를 패키지에 넣지 않았다. 원본 부팅 시도는 클래스 부재를 잡고 넘어간다. |

## 로더와 대상

- `Bridge` 등의 소스는 무선 CarPlay 페이로드에 있다. 코어 빌드가 페이로드의 `hmgapi/hook/*.java.src`와 `hmgapi/engine/*.java.src` 위에 `core/hook/src`를 덮어써 런타임 JAR과 SDK를 생성한다. [코어 빌드](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/core/hook/build.sh#L31) · [Bridge](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/modules/wireless-carplay-and-aa/payload/src/hmgapi/hook/Bridge.java.src#L67) · [ModContext](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/core/hook/src/hmgapi/hook/ModContext.java#L12)
- 코어는 부모 우선 `DexClassLoader`를 사용한다. 테마의 훅 API 타입 디스크립터 여섯 개를 같은 길이의 `gl3ccnc.api`로 옮겨 기존 DEX ID 순서를 유지했다. 코어 클래스는 컴파일 및 검증에만 사용했다. 원본과 링크된 DEX의 선언 283개 클래스, 1,212개 메서드 및 실행 본문 1,162개를 대조했다. [코어 로더](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/core/hook/src/hmgapi/hook/HmgApi.java#L128)
- `hook_apps` 대상은 `com.mobis.splitscreen.right`, `com.mnsoft.navi`, `com.daudio.app.dipo`다. 원본 `UniversalEntry.appLoaded`의 DEX 코드 항목 `0x0383b0`에서 분할화면과 DiPO 분기를, `NavigationHooks.appLoaded`의 `0x030dd0`에서 분할화면과 내비게이션 분기를 확인했다. DiPO 분기는 `NotificationManager.notify(String, int, Notification)`를 후킹해 CarPlay 음악 알림을 처리한다. 미디어 위젯 브로드캐스트는 테마가 해당 앱에서 처리한다.
- 자이고트는 활성 차량 맵의 제품, 펌웨어 경로, Android 버전, 순정 파일 해시와 프레임워크 훅포인트 네 개를 확인한 뒤 모듈을 로드한다. 제공된 소스의 맵은 아이오닉 5 KR용이다. `cars=GL3*`는 적용 가능 제품 필터다. K8용 맵 및 앱 메서드 시그니처, Dalvik 네이티브 훅 동작은 실차 확인이 필요하다. [코어 맵 확인](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/core/hook/src/hmgapi/hook/HmgApi.java#L63) · [모듈 제품 필터](https://github.com/seogaemo/hmg-seogaemo/blob/2f0ad48c228932bc5f5639ea59eac9a1e40b260a/nemesis/package/core/hsm-module.sh#L46)

원본 `hooks.jar` SHA-256은 `3da93a80042227092d86f31d7cd9299c328eb8e2de80cc7ede71449384d8e28c`다. `classes.dex` SHA-256은 `542e2c2ed16ce270fe7f6d5efb1c4840b76f884cb8fada6532cd152afcb6eb6e`다.
