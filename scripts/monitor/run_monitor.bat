@echo off
REM ============================================================
REM  COCHING 워크플로우 모니터 — Windows 실행 배치 파일
REM  사용법:
REM    run_monitor.bat            -> 텍스트 출력 (기본)
REM    run_monitor.bat html       -> HTML 리포트 생성
REM    run_monitor.bat json       -> JSON 출력
REM    run_monitor.bat gui        -> GUI 모니터 실행 (데스크톱 앱)
REM ============================================================

setlocal

REM 스크립트 위치로 이동
cd /d "%~dp0"

REM Python 경로 (PATH에 python이 없으면 전체 경로로 수정)
set PYTHON=python

REM GUI 모드
if /I "%1"=="gui" (
    echo [COCHING Monitor] GUI 모드 시작...
    start "" %PYTHON%w workflow_monitor_gui.pyw
    exit /b 0
)

REM 출력 형식 파라미터 (기본: text)
set FORMAT=text
if not "%1"=="" set FORMAT=%1

echo [COCHING Monitor] 시작: %date% %time%
echo [COCHING Monitor] 포맷: %FORMAT%
echo.

%PYTHON% workflow_monitor.py --format %FORMAT%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [오류] 모니터 스크립트 실행 실패 ^(종료코드: %ERRORLEVEL%^)
    echo Python 3 이 설치되어 있는지 확인하세요.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [COCHING Monitor] 완료: %date% %time%

REM HTML 모드인 경우 브라우저로 바로 열기
if "%FORMAT%"=="html" (
    set REPORT=E:\COCHING-WORKFLOW\reports\monitor_report.html
    if exist "%REPORT%" (
        echo [COCHING Monitor] 브라우저로 리포트를 엽니다...
        start "" "%REPORT%"
    )
)

endlocal
