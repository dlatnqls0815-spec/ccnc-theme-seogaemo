# ccNC Theme for 5W — HMG-Seogaemo(서개모) 이식 도구

blackr의 [ccNC Theme for 5W](https://github.com/b-lack-kr/ccnc-theme-for-5w)(HMG-API 모드)를
**HMG-Seogaemo(서개모)** 에서 돌아가는 `.hsm` 모듈로 바꿔 주는 빌드 도구입니다.
HMG-API를 따로 깔지 않고, 서개모를 그대로 둔 채 테마를 쓸 수 있게 합니다.

> **이 저장소에는 테마 자체가 들어 있지 않습니다.** 원본 테마의 저작권은 blackr에게 있습니다(All rights reserved).
> 빌드할 때 `tools/fetch_upstream.py`가 원작자의 GitHub 릴리스에서 직접 받아 옵니다.
> 만든 `.hsm`은 본인 차량에서만 쓰고, 다시 배포하지 마세요.

## 상태

- 만든 사람 차: 기아 K8(GL3) Gen5W, 서개모 0.1.54. 무선 ADB로 설치하고 켜서 **실차에서 잘 동작하는 것을 확인했습니다.** (2026-11-19, 기능별 세부 확인은 계속 추가합니다.)
- 원본 테마가 검증된 차는 아이오닉 5(NE)입니다. 다른 차에서는 일부 기능이 안 될 수 있습니다.
- 설치로 생기는 문제의 책임은 사용자에게 있습니다.

## 되는 것 / 빠진 것

| 기능 | 이식판 |
|---|---|
| 지도 아래 미디어 정보(곡명·앨범아트·진행선), 미디어 창 밀기 | 원본 코드 그대로 |
| 오른쪽 패널 손잡이·위젯, ccNC 스타일 길안내 버튼, 화이트/블랙 | 원본 코드 그대로 |
| CarPlay 음악 알림 연동(DiPO) | 원본 코드 그대로 |
| NAV 버튼 짧게/길게 바꾸기, 음성 검색 | **빠짐** (HMG-API 엔진 기능) |
| 바로가기 앱(Shortcuts.apk) | **빠짐** (서개모 외부 모듈은 앱 설치 불가) |
| 설정 즉시 반영 | 재시작 후 반영 |

어떻게 이었는지는 [API_GAP.md](API_GAP.md)에 있습니다. 원본 `hooks.jar`의 HMG-API 참조 6개 타입을 같은 길이의 `gl3ccnc.api` 어댑터로 바꾸고,
어댑터가 서개모 훅 API로 넘깁니다. 원본 테마의 클래스 283개·메서드 1,212개는 바뀌지 않았는지 빌드 때마다 대조합니다.

## 빌드

필요한 것: Python 3.10+ (`pip install cryptography`), JDK 17, Android SDK(platform `android-35`, build-tools `34.0.0`).

```bash
python tools/fetch_upstream.py
python build.py                       # → dist/ccnc-theme-5w-0.1.31.hsm
python build.py --verify dist/ccnc-theme-5w-0.1.31.hsm
```

JDK·SDK 경로는 `JAVA_HOME`, `ANDROID_HOME` 환경 변수나 `--jdk`, `--sdk`로 지정합니다.
서명용 로컬 키는 처음 빌드할 때 `.build/`에 생깁니다. 올리거나 공유하지 마세요.

## 설치

**USB:** USB 최상위 `HSM/` 폴더에 `.hsm`을 넣고 → 서개모 → 모듈 → 추가 → 설치 → 켜기 → 헤드유닛 재시작.

**무선 ADB:** 서개모의 "무선 ADB" 모듈을 켜고, PC를 차와 같은 Wi-Fi에 연결한 뒤:

```bash
bash tools/install-wireless.sh status  <차IP>
bash tools/install-wireless.sh install <차IP>
bash tools/install-wireless.sh remove  <차IP>
```

`/data/local/tmp/hsm/<sha256>.hsm`(서개모 공식 받은편지함)에 올리고 md5를 대조한 뒤 `hmg-seogaemo-root module install`로 설치합니다.
설치 직후에는 꺼져 있습니다. 켜기와 재시작은 차 화면에서 합니다. ADB TCP 설정은 바꾸지 않습니다.

주의:
- 서개모가 현재 차량 맵을 확인하지 못했으면 모듈이 켜지지 않습니다(`check.sh`).
- 다른 Now Playing·분할화면 후킹 모듈과 같이 켜면 충돌할 수 있습니다.
- 끄려면 서개모에서 끄고 재시작하거나 `remove`를 쓰세요.

## 라이선스

이 저장소의 코드(어댑터, 빌드·설치 스크립트)는 [AGPL-3.0](LICENSE)입니다. HMG-Seogaemo(AGPL-3.0)의 훅 API에 맞춰 컴파일됩니다.
ccNC Theme for 5W는 이 라이선스에 포함되지 않으며 원작자의 조건을 따릅니다.
