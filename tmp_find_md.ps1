Get-ChildItem -Path 'c:\Users\Feng\Desktop\20260523' -Recurse -Include *.md -ErrorAction SilentlyContinue |
  Where-Object {
    $_.LastWriteTime -ge (Get-Date '2026-05-24 00:00') -and
    $_.FullName -notlike '*\.venv*' -and
    $_.FullName -notlike '*ref_libs*' -and
    $_.FullName -notlike '*node_modules*' -and
    $_.FullName -notlike '*\.qoder*'
  } |
  Sort-Object LastWriteTime -Descending |
  Select-Object LastWriteTime, Length, FullName |
  Format-Table -AutoSize -Wrap
