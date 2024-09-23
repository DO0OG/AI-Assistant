::[Bat To Exe Converter]
::
::YAwzoRdxOk+EWAjk
::fBw5plQjdCuDJGmW+0g1Kw9oeguLP26ZCbgR6eb/0+OErUNTXeEwGA==
::YAwzuBVtJxjWCl3EqQJgSA==
::ZR4luwNxJguZRRnk
::Yhs/ulQjdF+5
::cxAkpRVqdFKZSjk=
::cBs/ulQjdF+5
::ZR41oxFsdFKZSDk=
::eBoioBt6dFKZSDk=
::cRo6pxp7LAbNWATEpCI=
::egkzugNsPRvcWATEpCI=
::dAsiuh18IRvcCxnZtBJQ
::cRYluBh/LU+EWAnk
::YxY4rhs+aU+JeA==
::cxY6rQJ7JhzQF1fEqQJQ
::ZQ05rAF9IBncCkqN+0xwdVs0
::ZQ05rAF9IAHYFVzEqQJQ
::eg0/rx1wNQPfEVWB+kM9LVsJDGQ=
::fBEirQZwNQPfEVWB+kM9LVsJDGQ=
::cRolqwZ3JBvQF1fEqQJQ
::dhA7uBVwLU+EWDk=
::YQ03rBFzNR3SWATElA==
::dhAmsQZ3MwfNWATElA==
::ZQ0/vhVqMQ3MEVWAtB9wSA==
::Zg8zqx1/OA3MEVWAtB9wSA==
::dhA7pRFwIByZRRnk
::Zh4grVQjdCuDJGmW+0g1Kw9oeguLP26ZCbgR6eb/08uVqwMYTOdf
::YB416Ek+ZG8=
::
::
::978f952a14a936cc963da21a135fa983
@echo off
setlocal

REM ë¡œê·¸ ?Œì¼ ê²½ë¡œ ?¤ì •
set logFile=logfile.log

REM ?„ìž¬ ?”ë ‰?°ë¦¬???ˆëŠ” Main.py ?¤í–‰
set pythonPath=pythonw
set scriptPath=Main.py

REM pythonw ?¤í–‰ ë¡œê·¸ (ë°±ê·¸?¼ìš´?œì—??
start /B %pythonPath% %scriptPath% >> %logFile% 2>&1

endlocal