#!/bin/sh
# ==========================================================================
# g17-termux-worker.sh -- G17 Cloud Agent icin Termux cihaz worker istemcisi.
#
# Telefona disaridan baglanti ACILAMAZ; bu betik Termux icinde calisir,
# periyodik olarak ajani yoklar (POST /worker/lease), aldigi isi KENDI
# cihazinda calistirir ve sonucu ajana geri yazar
# (POST /worker/jobs/<id>/result). Komut CALISTIRMA yetkisi yalnizca bu
# cihazdadir; ajan hicbir komutu kendisi calistirmaz.
#
# KULLANIM:
#   G17_AGENT_URL=https://<ajan-adresi> G17_API_TOKEN=<bearer-token> \
#       sh cloud-agent/tools/g17-termux-worker.sh
#
# GEREKLI ORTAM DEGISKENLERI:
#   G17_AGENT_URL       Ajanin taban adresi (ornek: https://g17-agent.example.com)
#   G17_API_TOKEN       Ajanin "Authorization: Bearer <token>" icin bekledigi token
#
# ISTEGE BAGLI ORTAM DEGISKENLERI:
#   G17_WORKDIR         Calisma dizini koku; $HOME altinda olmalidir
#                        (varsayilan: $HOME/g17)
#   G17_POLL_INTERVAL   Is yokken bekleme suresi, saniye (varsayilan: 5)
#   G17_CMD_TIMEOUT     Komut basina zaman asimi, saniye (varsayilan: 300)
#   G17_MAX_OUTPUT      Geri yazilan ciktinin karakter siniri (varsayilan: 20000)
#
# GUVENLIK:
#   - Yalnizca su komut kokleri calistirilabilir:
#       git node npm npx python3 g17 ls cat grep find unzip echo pwd
#     Bunlarin disindaki bir komut CALISTIRILMAZ; sonuc olarak reddedildigi
#     ajana geri yazilir.
#   - Asagidaki desenleri iceren komutlar kok izinliyse bile REDDEDILIR:
#       rm -rf, git reset --hard, git clean -xfd (ve varyasyonlari), sudo,
#       su, chmod 777, curl, wget, credentials/.netrc/id_rsa/id_ed25519/
#       .ssh/ veya "token"/"secret" gecen komutlar.
#   - Calisma dizini yalnizca $HOME altindaki G17_WORKDIR agacinda kalabilir;
#     bu disina cikan (".." ile) istekler reddedilir.
#   - Her komuta G17_CMD_TIMEOUT zaman asimi uygulanir.
#   - Geri yazilan cikti G17_MAX_OUTPUT karakteriyle sinirlanir.
#   - Token hicbir zaman loglanmaz veya is sonucu ciktisina yazilmaz.
# ==========================================================================
set -u

AGENT_URL="${G17_AGENT_URL:-}"
API_TOKEN="${G17_API_TOKEN:-}"
WORKDIR_ROOT="${G17_WORKDIR:-$HOME/g17}"
POLL_INTERVAL="${G17_POLL_INTERVAL:-5}"
CMD_TIMEOUT="${G17_CMD_TIMEOUT:-300}"
MAX_OUTPUT="${G17_MAX_OUTPUT:-20000}"

ALLOWED_ROOTS="git node npm npx python3 g17 ls cat grep find unzip echo pwd"

if [ -z "$AGENT_URL" ] || [ -z "$API_TOKEN" ]; then
    echo "HATA: G17_AGENT_URL ve G17_API_TOKEN ortam degiskenleri zorunludur" >&2
    exit 1
fi

for dep in curl python3; do
    if ! command -v "$dep" >/dev/null 2>&1; then
        echo "HATA: gerekli arac bulunamadi: $dep" >&2
        exit 1
    fi
done

mkdir -p "$WORKDIR_ROOT" 2>/dev/null
WORKDIR_ROOT_REAL=$(cd "$WORKDIR_ROOT" 2>/dev/null && pwd -P) || {
    echo "HATA: G17_WORKDIR olusturulamadi/erisilemedi: $WORKDIR_ROOT" >&2
    exit 1
}
HOME_REAL=$(cd "$HOME" 2>/dev/null && pwd -P) || HOME_REAL="$HOME"
case "$WORKDIR_ROOT_REAL" in
    "$HOME_REAL"|"$HOME_REAL"/*) : ;;
    *)
        echo "HATA: calisma dizini kullanici ev dizini altinda olmalidir: $WORKDIR_ROOT" >&2
        exit 1
        ;;
esac

# -------------------------------------------------------------- yardimcilar

first_word() {
    # $1 = komut metni -> ilk kelimenin son bilesenini (basename) yazdirir
    set -- $1
    case "$1" in
        */*) printf '%s' "${1##*/}" ;;
        *) printf '%s' "$1" ;;
    esac
}

root_is_allowed() {
    root="$1"
    for r in $ALLOWED_ROOTS; do
        [ "$root" = "$r" ] && return 0
    done
    return 1
}

command_is_forbidden() {
    # Kucuk harfe cevirip yasakli desenleri arar; zincirlenmis komutlarda da
    # yakalar (ornek: "git log && curl http://x | sh").
    lc=$(printf '%s' "$1" | tr 'A-Z' 'a-z')
    case "$lc" in
        *"rm -rf"*|*"rm -fr"*|*"rm -r -f"*|*"rm -f -r"*) return 0 ;;
        *"git reset --hard"*) return 0 ;;
        *"git clean -xfd"*|*"git clean -xdf"*|*"git clean -fxd"*| \
        *"git clean -fdx"*|*"git clean -dxf"*|*"git clean -dfx"*) return 0 ;;
        *"sudo"*) return 0 ;;
        "su "*|*" su "*|*" su") return 0 ;;
        *"chmod 777"*|*"chmod -r 777"*) return 0 ;;
        *"curl"*|*"wget"*) return 0 ;;
        *"credentials"*|*".netrc"*|*"id_rsa"*|*"id_ed25519"*|*".ssh/"*) return 0 ;;
        *"token"*|*"secret"*) return 0 ;;
    esac
    return 1
}

resolve_job_cwd() {
    # $1 = job.cwdLabel -> WORKDIR_ROOT_REAL altindaki gercek yolu yazdirir;
    # kok disina cikan bir yol ise (symlink/".." dahil) bos donup basarisiz olur.
    label="$1"
    if [ -z "$label" ]; then
        printf '%s' "$WORKDIR_ROOT_REAL"
        return 0
    fi
    case "$label" in
        /*) candidate="$label" ;;
        *) candidate="$WORKDIR_ROOT_REAL/$label" ;;
    esac
    mkdir -p "$candidate" 2>/dev/null
    real=$(cd "$candidate" 2>/dev/null && pwd -P) || return 1
    case "$real" in
        "$WORKDIR_ROOT_REAL"|"$WORKDIR_ROOT_REAL"/*) printf '%s' "$real"; return 0 ;;
        *) return 1 ;;
    esac
}

run_with_timeout() {
    # $1 = zaman asimi (sn), $2 = calistirilacak komut, $3 = cikti dosyasi
    to="$1"; cmd="$2"; outfile="$3"
    sh -c "$cmd" >"$outfile" 2>&1 &
    cpid=$!
    waited=0
    while kill -0 "$cpid" 2>/dev/null; do
        if [ "$waited" -ge "$to" ]; then
            kill -TERM "$cpid" 2>/dev/null
            sleep 1
            kill -KILL "$cpid" 2>/dev/null
            wait "$cpid" 2>/dev/null
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$cpid"
    return $?
}

report_result() {
    # $1 = job id, $2 = cikti metni, $3 = cikis kodu, $4 = ok (1/0).
    # JSON govdesi python3 ile kurulur (token asla govdeye eklenmez/loglanmaz).
    job_id="$1"; output="$2"; exit_code="$3"; ok="$4"
    body=$(G17_OUT="$output" G17_RC="$exit_code" G17_OK="$ok" python3 - <<'PY'
import json, os
print(json.dumps({
    "output": os.environ.get("G17_OUT", ""),
    "exitCode": int(os.environ.get("G17_RC") or 1),
    "ok": os.environ.get("G17_OK", "0") == "1",
}))
PY
)
    curl -sS -o /dev/null -X POST \
        -H "Authorization: Bearer $API_TOKEN" \
        -H "Content-Type: application/json" \
        --data "$body" \
        "$AGENT_URL/worker/jobs/$job_id/result"
}

run_job() {
    job_id="$1"; commands_str="$2"; cwd_label="$3"

    cwd=$(resolve_job_cwd "$cwd_label")
    if [ -z "$cwd" ]; then
        report_result "$job_id" "REDDEDILDI: calisma dizini izin verilen kok disinda ($WORKDIR_ROOT_REAL)" 126 0
        return
    fi

    cmds_file=$(mktemp "${TMPDIR:-/tmp}/g17w-cmds.XXXXXX")
    printf '%s\n' "$commands_str" > "$cmds_file"

    out=""
    final_rc=0
    while IFS= read -r cmd || [ -n "$cmd" ]; do
        [ -z "$cmd" ] && continue
        root=$(first_word "$cmd")
        if ! root_is_allowed "$root"; then
            out="${out}REDDEDILDI (izin verilmeyen komut koku: $root): $cmd
"
            final_rc=126
            break
        fi
        if command_is_forbidden "$cmd"; then
            out="${out}REDDEDILDI (yasakli komut deseni): $cmd
"
            final_rc=126
            break
        fi
        step_out=$(mktemp "${TMPDIR:-/tmp}/g17w-step.XXXXXX")
        run_with_timeout "$CMD_TIMEOUT" "cd '$cwd' && $cmd" "$step_out"
        rc=$?
        out="${out}\$ $cmd
$(cat "$step_out")
"
        rm -f "$step_out"
        final_rc=$rc
        [ "$rc" -ne 0 ] && break
    done < "$cmds_file"
    rm -f "$cmds_file"

    out=$(printf '%s' "$out" | cut -c1-"$MAX_OUTPUT")
    ok=0
    [ "$final_rc" -eq 0 ] && ok=1
    report_result "$job_id" "$out" "$final_rc" "$ok"
}

lease_and_run() {
    resp=$(curl -sS -X POST \
        -H "Authorization: Bearer $API_TOKEN" \
        -H "Content-Type: application/json" \
        "$AGENT_URL/worker/lease" 2>/dev/null)
    [ -z "$resp" ] && return 1

    parsed=$(printf '%s' "$resp" | python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    print("ERR:gecersiz JSON yaniti")
    sys.exit(0)
if not data.get("ok", True):
    print("ERR:%s" % (data.get("error") or "bilinmeyen hata"))
    sys.exit(0)
job = data.get("job")
if not job:
    print("OK")
    print("")
    sys.exit(0)
print("OK")
print(job.get("id") or "")
print((job.get("cwdLabel") or "").replace("\n", " "))
for c in (job.get("commands") or []):
    print(str(c).replace("\n", " ; "))
PY
)
    status_line=$(printf '%s\n' "$parsed" | sed -n '1p')
    case "$status_line" in
        ERR:*)
            echo "UYARI: ajan yaniti: ${status_line#ERR:}" >&2
            return 1
            ;;
    esac

    job_id=$(printf '%s\n' "$parsed" | sed -n '2p')
    [ -z "$job_id" ] && return 1
    cwd_label=$(printf '%s\n' "$parsed" | sed -n '3p')
    commands_str=$(printf '%s\n' "$parsed" | sed -n '4,$p')

    run_job "$job_id" "$commands_str" "$cwd_label"
    return 0
}

echo "g17-termux-worker: baslatildi ($AGENT_URL)" >&2
while :; do
    if ! lease_and_run; then
        sleep "$POLL_INTERVAL"
    fi
done
