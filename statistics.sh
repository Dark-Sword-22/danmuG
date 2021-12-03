# find . "(" -name "*.py" -or -name "*.pyx" -or -name "*.vpy" ")" -print | xargs wc -l
# find . "(" -name "*.vue" -or -name "*.js" ")" -print | xargs wc -l
# find . "(" -name "*.c" -or -name "*.cpp" ")" -print | xargs wc -l
# find . "(" -name "*.py" -or -name "*.pyx" -or -name "*.vpy" -or -name "*.vue" -or -name "*.js" -or -name "*.c" -or -name "*.cpp" ")" -print | xargs wc -l
# echo "按任意键继续"
# read -n 1
tokei
echo "按任意键继续"
read -n 1