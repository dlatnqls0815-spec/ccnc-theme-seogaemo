#!/usr/bin/env bash
# 무선 ADB로 ccnc-theme-5w 서개모 모듈을 설치/확인/제거한다 (bash / Git Bash).
#
#   bash out/tools/install-wireless.sh install <차IP>    설치 (켜기·재시작은 서개모 앱에서 직접)
#   bash out/tools/install-wireless.sh status  <차IP>    설치 여부만 읽기
#   bash out/tools/install-wireless.sh remove  <차IP>    모듈 제거
#   DRY_RUN=1 bash ... 로 실행하면 차에 아무것도 보내지 않고 할 일만 출력한다.
#
# 전제: 서개모의 "무선 ADB" 모듈이 켜져 있고, PC가 차와 같은 Wi-Fi(차량 핫스팟 등)에 있다.
# 이 스크립트는 ADB TCP 설정(persist.service.adb.tcp.enable 등)을 바꾸지 않는다.
# 서개모 공식 경로만 쓴다: /data/local/tmp/hsm/<sha256>.hsm 받은편지함 → hmg-seogaemo-root module install <sha256>.
# 차 IP는 인수로만 받고 어디에도 저장하지 않는다.
set -euo pipefail
export MSYS_NO_PATHCONV=1

HERE=$(cd "$(dirname "$0")" && pwd)
HSM=${HSM:-$HERE/../dist/ccnc-theme-5w-0.1.31.hsm}
MOD_ID=ccnc-theme-5w
ADB=${ADB:-$(command -v adb || echo adb)}
ROOT_CMD=/data/nemesis/apps/hmg-seogaemo/bin/hmg-seogaemo-root
INBOX=/data/local/tmp/hsm
PORT=5555

cmd=${1:-}; ip=${2:-}
case "$cmd" in install|status|remove) ;; *) sed -n '2,7s/^# \{0,1\}//p' "$0"; exit 2;; esac
[[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo "차 IP를 x.x.x.x 형식으로 주세요"; exit 2; }
DEV=$ip:$PORT

run() { if [ "${DRY_RUN:-0}" = 1 ]; then echo "[DRY] $*"; else "$@"; fi; }
sh_dev() { run "$ADB" -s "$DEV" shell "$1" | tr -d '\r'; }
root_dev() { sh_dev "nemesis root -c '$1'"; }

command -v "$ADB" >/dev/null || [ -x "$ADB" ] || { echo "adb가 없어요. Android platform-tools를 설치하거나 ADB=<경로> 로 지정하세요"; exit 1; }
if [ "$cmd" = install ]; then
    [ -f "$HSM" ] || { echo "설치 파일이 없어요: $HSM"; exit 1; }
    SHA=$(sha256sum "$HSM" | cut -d' ' -f1)
    MD5=$(md5sum "$HSM" | cut -d' ' -f1)
    if [ -f "$HSM.sha256" ] && ! grep -q "$SHA" "$HSM.sha256"; then echo "설치 파일 해시가 .sha256과 달라요"; exit 1; fi
fi

echo "== 1. 무선 ADB 연결 ($ip:$PORT)"
run "$ADB" connect "$DEV" | tr -d '\r'
if [ "${DRY_RUN:-0}" != 1 ]; then
    [ "$("$ADB" -s "$DEV" get-state 2>/dev/null | tr -d '\r')" = device ] || { echo "연결 실패: 서개모 무선 ADB가 켜져 있는지, 같은 Wi-Fi인지 확인하세요"; exit 1; }
fi

echo "== 2. 서개모 확인 (읽기 전용)"
if [ "${DRY_RUN:-0}" != 1 ]; then
    [ "$(sh_dev "[ -f $ROOT_CMD ] && echo yes")" = yes ] || { echo "서개모(hmg-seogaemo)가 설치돼 있지 않아요. 중단합니다."; exit 1; }
fi
root_dev "/system/bin/sh $ROOT_CMD module list" | grep -E "$MOD_ID|^state=|^detail=" || echo "(이 모듈은 아직 목록에 없음)"

if [ "$cmd" = status ]; then
    echo "== 겹치는 미디어 모듈 확인 (k8-nowplaying 등)"
    sh_dev "ls /data/nemesis/apps 2>/dev/null" | grep -i -E "nowplaying" || echo "(nowplaying 패키지 없음)"
    exit 0
fi

if [ "$cmd" = remove ]; then
    echo "== 3. 제거"
    root_dev "/system/bin/sh $ROOT_CMD module remove $MOD_ID"
    echo "완료. 헤드유닛을 재시작하면 순정 화면으로 돌아와요."
    exit 0
fi

echo "== 3. 겹치는 미디어 모듈 확인"
if sh_dev "ls /data/nemesis/apps 2>/dev/null" | grep -i -E "nowplaying|k8np"; then
    echo "주의: Now Playing 계열 패키지가 있어요. 테마를 켜기 전에 그쪽을 꺼야 충돌하지 않아요."
fi

echo "== 4. 파일 전송 → $INBOX/$SHA.hsm"
sh_dev "mkdir -p $INBOX && chmod 755 $INBOX"
HSM_LOCAL=$HSM; command -v cygpath >/dev/null && HSM_LOCAL=$(cygpath -w "$HSM")   # adb.exe needs a Windows path
run "$ADB" -s "$DEV" push "$HSM_LOCAL" "$INBOX/$SHA.hsm" | tr -d '\r'
if [ "${DRY_RUN:-0}" != 1 ]; then
    got=$(sh_dev "md5 $INBOX/$SHA.hsm" | cut -d' ' -f1)
    [ "$got" = "$MD5" ] || { echo "전송된 파일 md5가 달라요($got). 파일을 지우고 중단합니다."; sh_dev "rm -f $INBOX/$SHA.hsm"; exit 1; }
    echo "md5 일치: $MD5"
fi

echo "== 5. 서개모로 설치 (설치 직후 모듈은 꺼진 상태)"
out=$(root_dev "/system/bin/sh $ROOT_CMD module install $SHA" || true)
echo "$out"
sh_dev "rm -f $INBOX/$SHA.hsm"

echo "== 6. 설치 확인"
[ "${DRY_RUN:-0}" = 1 ] && { echo "[DRY] 여기까지. 차에는 아무것도 보내지 않았어요."; exit 0; }
root_dev "/system/bin/sh $ROOT_CMD module list" | grep -E "$MOD_ID" || { echo "목록에 $MOD_ID 가 없어요. 위 출력의 detail= 줄을 확인하세요."; exit 1; }

cat <<'EOF'

설치됐어요. 다음은 차 화면에서 직접 하세요:
  1. 서개모 → 모듈 → "ccNC 테마 for 5W" 켜기 (차량 맵 확인이 안 됐으면 켜지지 않고 안내가 나와요)
  2. 헤드유닛 재시작
  3. 분할화면·내비·미디어 정보·후방 카메라가 정상인지 확인
되돌리기: 서개모에서 끄고 재시작, 또는  bash out/tools/install-wireless.sh remove <차IP>
EOF
