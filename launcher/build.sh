#!/bin/zsh
# ダブルクリックでクイズアプリを起動する「AWS SAA Quiz.app」を作る(macOS専用)
# 使い方: ./launcher/build.sh [出力先フォルダ(省略時はデスクトップ)]
set -euo pipefail

launcher_dir="${0:A:h}"
project_dir="${launcher_dir:h}"
out_dir="${1:-$HOME/Desktop}"
app="$out_dir/AWS SAA Quiz.app"

uv_path="$(command -v uv)" || { echo "uv が見つかりません。先に uv をインストールしてください。" >&2; exit 1; }

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
script="$tmp_dir/launcher.applescript"
sed -e "s|__PROJECT_DIR__|$project_dir|" -e "s|__UV__|$uv_path|" \
  "$launcher_dir/launcher.applescript" > "$script"

rm -rf "$app"
osacompile -o "$app" "$script"

# 標準のスクリプトアイコン(Assets.car)ではなく AppIcon.icns を使わせる
cp "$launcher_dir/AppIcon.icns" "$app/Contents/Resources/applet.icns"
/usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$app/Contents/Info.plist" 2>/dev/null || true
rm -f "$app/Contents/Resources/Assets.car"

codesign --force --deep -s - "$app" 2>/dev/null
touch "$app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"

echo "作成しました: $app"
