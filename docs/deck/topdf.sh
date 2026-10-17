#!/bin/bash
# usage: topdf.sh in.pptx out.pdf — Keynote で開いて PDF に書き出す（見た目の確認用）
K=~/Library/Containers/com.apple.iWork.Keynote/Data/tmp
N="qa-$(date +%s%N)"
mkdir -p "$K"
cp "$1" "$K/$N.pptx"; rm -f "$K/$N.pdf"
osascript -e 'tell application "Keynote" to close every document saving no' 2>/dev/null
open -a Keynote "$K/$N.pptx"
for i in $(seq 1 30); do
  osascript -e "tell application \"Keynote\" to get name of every document" 2>/dev/null | grep -q "$N" && break; sleep 1
done
osascript -e "tell application \"Keynote\" to export (first document whose name contains \"$N\") to POSIX file \"$K/$N.pdf\" as PDF" \
          -e "tell application \"Keynote\" to close (first document whose name contains \"$N\") saving no"
mv "$K/$N.pdf" "$2"; rm -f "$K/$N.pptx"
