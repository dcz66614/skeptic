# VHS tape for a short Skeptic demo.
# Run from the repository root:
#   vhs docs/launch/demo.tape
# TypingSpeed is 12ms. The Sleep lines below total 13s.
# With typing, the recording stays under 30 seconds.
# Shell is whatever vhs inherits. The three commands are the same in pwsh and bash.
# The committed demo.gif is a frame render of these commands captured on this tree.

Output docs/launch/demo.gif

Set FontSize 18
Set Width 1100
Set Height 700
Set Padding 20
Set TypingSpeed 12ms

Type "uv run skeptic --version"
Enter
Sleep 2s

Type "uv run skeptic faults list --class silent"
Enter
Sleep 5s

Type "uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --count"
Enter
Sleep 6s
