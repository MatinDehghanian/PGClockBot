# PGClockBot — Easy interactive installer (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Info($m) { Write-Host "-> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "OK $m" -ForegroundColor Green }
function Write-Err($m)  { Write-Host "X  $m" -ForegroundColor Red }

function Ask([string]$Prompt, [string]$Default = "") {
    if ($Default) {
        $v = Read-Host "$Prompt [$Default]"
        if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
        return $v
    }
    while ($true) {
        $v = Read-Host $Prompt
        if (-not [string]::IsNullOrWhiteSpace($v)) { return $v }
        Write-Err "این فیلد الزامی است."
    }
}

function Test-Password([string]$p) {
    if ($p.Length -lt 8) { Write-Err "پسورد باید حداقل ۸ کاراکتر باشد."; return $false }
    if ($p -notmatch "[A-Z]") { Write-Err "پسورد باید حداقل یک حرف بزرگ انگلیسی داشته باشد."; return $false }
    if ($p -notmatch "[^a-zA-Z0-9]") { Write-Err "پسورد باید حداقل یک کاراکتر خاص داشته باشد."; return $false }
    return $true
}

function Ask-Password([string]$Prompt) {
    while ($true) {
        $p1 = Read-Host $Prompt -AsSecureString
        $b1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($p1))
        if (-not (Test-Password $b1)) { continue }
        $p2 = Read-Host "تکرار پسورد" -AsSecureString
        $b2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($p2))
        if ($b1 -ne $b2) { Write-Err "پسوردها یکسان نیستند."; continue }
        return $b1
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "   PGClockBot — نصب آسان (Windows)"
Write-Host "========================================"
Write-Host ""

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Err "Python پیدا نشد."; exit 1 }
Write-Ok "Python پیدا شد"

Write-Info "مرحله ۱ — تلگرام"
$BOT_TOKEN = Ask "توکن ربات (از BotFather)"
$BOT_USERNAME = Ask "یوزرنیم ربات بدون @" "PGClockBot"
$ADMIN_IDS = Ask "آیدی عددی ادمین(ها) — چندتایی با ویرگول"

Write-Info "مرحله ۲ — پاسارگارد"
$PG_BASE_URL = (Ask "آدرس پنل پاسارگارد" "https://dev.mrclock.website").TrimEnd("/")
$PG_USERNAME = Ask "یوزرنیم ادمین پاسارگارد"
$PG_PASSWORD = Ask "رمز عبور ادمین پاسارگارد"

Write-Info "مرحله ۳ — وب‌پنل"
$WEB_PORT = Ask "پورت وب‌پنل" "9000"
$WEB_ADMIN_USER = Ask "نام کاربری ورود وب‌پنل" "admin"
Write-Host "قوانین پسورد: حداقل ۸ کاراکتر + حرف بزرگ + کاراکتر خاص"
$WEB_ADMIN_PASSWORD = Ask-Password "پسورد وب‌پنل"
$WEB_SECRET = -join ((1..48) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })

Write-Info "مرحله ۴ — اختیاری"
$PUBLIC_BASE_URL = Ask "آدرس HTTPS مینی‌اپ (خالی = بدون مینی‌اپ)" ""
$CURRENCY = Ask "واحد پول" "تومان"

Write-Info "مرحله ۵ — نصب پکیج‌ها"
if (-not (Test-Path .venv)) {
    python -m venv .venv
    Write-Ok "venv ساخته شد"
}
& .\.venv\Scripts\python.exe -m pip install -U pip wheel | Out-Null
& .\.venv\Scripts\pip.exe install -r requirements.txt
Write-Ok "پکیج‌ها نصب شدند"

@"
BOT_TOKEN=$BOT_TOKEN
BOT_USERNAME=$BOT_USERNAME
ADMIN_IDS=$ADMIN_IDS
PG_BASE_URL=$PG_BASE_URL
PG_USERNAME=$PG_USERNAME
PG_PASSWORD=$PG_PASSWORD
WEB_HOST=0.0.0.0
WEB_PORT=$WEB_PORT
WEB_SECRET=$WEB_SECRET
WEB_ADMIN_USER=$WEB_ADMIN_USER
WEB_ADMIN_PASSWORD=$WEB_ADMIN_PASSWORD
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
WEBHOOK_URL=
WEBHOOK_PATH=/telegram/webhook
PUBLIC_BASE_URL=$PUBLIC_BASE_URL
CURRENCY=$CURRENCY
DEFAULT_LOCALE=fa
"@ | Set-Content -Path .env -Encoding UTF8

New-Item -ItemType Directory -Force -Path data | Out-Null
Write-Ok ".env ذخیره شد"

Write-Host ""
Write-Ok "نصب تمام شد"
Write-Host "وب‌پنل: http://127.0.0.1:$WEB_PORT  کاربر: $WEB_ADMIN_USER"
Write-Host "بقیه تنظیمات (دکمه‌ها، متن‌ها، پلن‌ها، کارت) از وب‌پنل."
Write-Host ""

$start = Ask "الان اجرا شود؟ (Y/n)" "Y"
if ($start -notmatch '^[nN]') {
    & .\.venv\Scripts\python.exe run.py
}
