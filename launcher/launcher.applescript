-- AWS SAA クイズアプリをターミナルなしで起動する
-- 下の projectDir と uvPath は build.sh が実際のパスに置き換える
property projectDir : "__PROJECT_DIR__"
property uvPath : "__UV__"
property appURL : "http://localhost:8501"
property logFile : "$HOME/Library/Logs/AWSSAAQuiz.log"

on isRunning()
	try
		do shell script "lsof -iTCP:8501 -sTCP:LISTEN >/dev/null 2>&1"
		return true
	on error
		return false
	end try
end isRunning

on run
	if isRunning() then
		set answer to button returned of (display dialog "クイズアプリは起動中です。" buttons {"アプリを終了", "ブラウザで開く"} default button "ブラウザで開く" with title "AWS SAA Quiz")
		if answer is "アプリを終了" then
			do shell script "lsof -tiTCP:8501 -sTCP:LISTEN | xargs kill"
		else
			open location appURL
		end if
		return
	end if

	do shell script "cd " & quoted form of projectDir & " && STREAMLIT_SERVER_HEADLESS=true nohup " & quoted form of uvPath & " run streamlit run app.py > \"" & logFile & "\" 2>&1 &"

	-- 起動完了を最大30秒待ってからブラウザを開く
	repeat 60 times
		if isRunning() then
			open location appURL
			return
		end if
		delay 0.5
	end repeat
	display dialog "起動に失敗しました。ログを確認してください:" & return & "~/Library/Logs/AWSSAAQuiz.log" buttons {"OK"} default button "OK" with icon stop with title "AWS SAA Quiz"
end run
