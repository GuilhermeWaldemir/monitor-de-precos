@echo off
rem Verificacao diaria de precos, chamada pelo Agendador de Tarefas do Windows (12:30).
rem Roda a partir da pasta do projeto, usando o Python do ambiente virtual (.venv).
cd /d "%~dp0.."
".venv\Scripts\pythonw.exe" -m monitor.daily_check
