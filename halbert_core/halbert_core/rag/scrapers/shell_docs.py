"""
Shell Scripting Documentation Scraper.

Phase 27: RAG Coverage

Comprehensive bash/shell guides covering:
- Bash fundamentals
- Shell scripting patterns
- Text processing (awk, sed, grep)
- Process management
- Common one-liners
"""

import logging
from typing import List
from datetime import datetime
from pathlib import Path

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class ShellDocsScraper(BaseScraper):
    """Generates comprehensive shell scripting documentation."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "shell-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        """Generate shell documentation."""
        logger.info("Generating shell documentation...")
        
        documents = []
        documents.extend(self._generate_guides())
        
        logger.info(f"Total shell documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        """Generate all shell guides."""
        guides = []
        
        guides.append(self._bash_basics_guide())
        guides.append(self._scripting_guide())
        guides.append(self._awk_guide())
        guides.append(self._sed_guide())
        guides.append(self._grep_guide())
        guides.append(self._find_xargs_guide())
        guides.append(self._process_guide())
        guides.append(self._oneliners_guide())
        
        return guides
    
    def _bash_basics_guide(self) -> ScrapedDocument:
        """Bash basics guide."""
        content = """# Bash Fundamentals

## Variables

```bash
# Set variable (no spaces around =)
name="value"
readonly CONSTANT="unchangeable"

# Use variable
echo $name
echo ${name}
echo "${name}_suffix"

# Default values
echo ${var:-default}      # Use default if unset
echo ${var:=default}      # Set and use default if unset
echo ${var:+alternate}    # Use alternate if set
echo ${var:?error msg}    # Error if unset

# String operations
${#string}                # Length
${string:0:5}             # Substring (start:length)
${string#pattern}         # Remove shortest prefix
${string##pattern}        # Remove longest prefix
${string%pattern}         # Remove shortest suffix
${string%%pattern}        # Remove longest suffix
${string/old/new}         # Replace first
${string//old/new}        # Replace all
```

## Arrays

```bash
# Indexed array
arr=(one two three)
arr[0]="first"

echo ${arr[0]}            # First element
echo ${arr[@]}            # All elements
echo ${#arr[@]}           # Array length
echo ${!arr[@]}           # All indices

# Associative array (bash 4+)
declare -A map
map[key]="value"
map["another"]="data"

echo ${map[key]}
echo ${!map[@]}           # All keys

# Iterate
for item in "${arr[@]}"; do
    echo "$item"
done

for key in "${!map[@]}"; do
    echo "$key: ${map[$key]}"
done
```

## Conditionals

```bash
# if statement
if [[ condition ]]; then
    commands
elif [[ other ]]; then
    commands
else
    commands
fi

# String comparisons
[[ "$a" == "$b" ]]        # Equal
[[ "$a" != "$b" ]]        # Not equal
[[ "$a" < "$b" ]]         # Less than (alphabetic)
[[ -z "$a" ]]             # Empty
[[ -n "$a" ]]             # Not empty
[[ "$a" =~ regex ]]       # Regex match

# Numeric comparisons
[[ $a -eq $b ]]           # Equal
[[ $a -ne $b ]]           # Not equal
[[ $a -lt $b ]]           # Less than
[[ $a -le $b ]]           # Less or equal
[[ $a -gt $b ]]           # Greater than
[[ $a -ge $b ]]           # Greater or equal

# File tests
[[ -e file ]]             # Exists
[[ -f file ]]             # Regular file
[[ -d dir ]]              # Directory
[[ -r file ]]             # Readable
[[ -w file ]]             # Writable
[[ -x file ]]             # Executable
[[ -s file ]]             # Non-empty
[[ file1 -nt file2 ]]     # Newer than
[[ file1 -ot file2 ]]     # Older than

# Logical operators
[[ cond1 && cond2 ]]      # AND
[[ cond1 || cond2 ]]      # OR
[[ ! condition ]]         # NOT
```

## Loops

```bash
# for loop
for i in 1 2 3 4 5; do
    echo $i
done

for i in {1..10}; do
    echo $i
done

for i in {1..10..2}; do   # Step by 2
    echo $i
done

for file in *.txt; do
    echo "$file"
done

# C-style for
for ((i=0; i<10; i++)); do
    echo $i
done

# while loop
while [[ condition ]]; do
    commands
done

# until loop
until [[ condition ]]; do
    commands
done

# Read file line by line
while IFS= read -r line; do
    echo "$line"
done < file.txt

# Infinite loop
while true; do
    commands
    sleep 1
done
```

## Functions

```bash
# Define function
function greet() {
    local name="$1"
    echo "Hello, $name!"
    return 0
}

# Or without 'function' keyword
greet() {
    local name="$1"
    echo "Hello, $name!"
}

# Call function
greet "World"

# Capture return value
greet "User"
status=$?

# Capture output
result=$(greet "User")
```

## Special Variables

```bash
$0          # Script name
$1..$9      # Positional parameters
${10}       # 10th parameter
$#          # Number of parameters
$@          # All parameters (separate words)
$*          # All parameters (single word)
$$          # Current PID
$!          # Last background PID
$?          # Last exit status
$_          # Last argument of previous command
```

## Arithmetic

```bash
# (( )) for arithmetic
((result = 5 + 3))
((count++))
((count += 5))

# $((  )) for expansion
echo $((5 + 3))
result=$((a * b))

# let command
let "result = 5 + 3"

# bc for floating point
result=$(echo "5.5 + 3.2" | bc)
result=$(echo "scale=2; 10/3" | bc)
```
"""
        return ScrapedDocument(
            id=self._generate_id("bash-basics"),
            url="https://www.gnu.org/software/bash/manual/",
            title="Bash Fundamentals",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["bash", "shell", "linux", "scripting"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _scripting_guide(self) -> ScrapedDocument:
        """Shell scripting patterns guide."""
        content = """# Shell Scripting Best Practices

## Script Template

```bash
#!/bin/bash
set -euo pipefail
IFS=$'\\n\\t'

# Description: What this script does
# Usage: ./script.sh [options] args

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"

# Constants
readonly LOG_FILE="/var/log/${SCRIPT_NAME}.log"

# Functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [options] <args>

Options:
    -h, --help      Show this help
    -v, --verbose   Verbose output
    -d, --dry-run   Don't make changes

EOF
    exit 0
}

# Main
main() {
    local verbose=false
    local dry_run=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help) usage ;;
            -v|--verbose) verbose=true; shift ;;
            -d|--dry-run) dry_run=true; shift ;;
            --) shift; break ;;
            -*) die "Unknown option: $1" ;;
            *) break ;;
        esac
    done

    # Your code here
    log "Starting $SCRIPT_NAME"
}

main "$@"
```

## Error Handling

```bash
# Exit on error
set -e                    # Exit on any error
set -u                    # Error on undefined variable
set -o pipefail           # Pipe fails if any command fails

# Trap errors
trap 'echo "Error on line $LINENO"' ERR

# Cleanup on exit
cleanup() {
    rm -f "$TEMP_FILE"
}
trap cleanup EXIT

# Check command success
if ! command -v docker &>/dev/null; then
    echo "docker not found"
    exit 1
fi

# Or inline
docker ps || { echo "docker failed"; exit 1; }
```

## Input Validation

```bash
# Check argument count
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <arg1> <arg2>"
    exit 1
fi

# Check file exists
[[ -f "$1" ]] || die "File not found: $1"

# Check directory
[[ -d "$1" ]] || mkdir -p "$1"

# Check command exists
command -v git &>/dev/null || die "git not installed"

# Validate number
if ! [[ "$1" =~ ^[0-9]+$ ]]; then
    die "Not a number: $1"
fi
```

## User Interaction

```bash
# Prompt for input
read -p "Enter name: " name

# Prompt with default
read -p "Enter name [default]: " name
name=${name:-default}

# Prompt for password (hidden)
read -sp "Password: " password
echo

# Yes/No confirmation
read -p "Continue? [y/N] " response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "Continuing..."
fi

# Menu selection
PS3="Select option: "
select opt in "Option 1" "Option 2" "Quit"; do
    case $opt in
        "Option 1") echo "Selected 1" ;;
        "Option 2") echo "Selected 2" ;;
        "Quit") break ;;
        *) echo "Invalid" ;;
    esac
done
```

## Temporary Files

```bash
# Create temp file
TEMP_FILE=$(mktemp)
TEMP_DIR=$(mktemp -d)

# With template
TEMP_FILE=$(mktemp /tmp/myapp.XXXXXX)

# Cleanup on exit
trap "rm -f $TEMP_FILE" EXIT

# Here document to file
cat > "$TEMP_FILE" <<EOF
Configuration content
Line 2
EOF
```

## Logging

```bash
# Simple logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

log_info()  { log "INFO:  $*"; }
log_warn()  { log "WARN:  $*" >&2; }
log_error() { log "ERROR: $*" >&2; }

# Log to file and stdout
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Verbose mode
VERBOSE=${VERBOSE:-false}
debug() {
    $VERBOSE && echo "DEBUG: $*" >&2
}
```

## Parallel Execution

```bash
# Background jobs
for file in *.txt; do
    process_file "$file" &
done
wait    # Wait for all

# Limit parallel jobs
MAX_JOBS=4
for file in *.txt; do
    while [[ $(jobs -r | wc -l) -ge $MAX_JOBS ]]; do
        sleep 0.1
    done
    process_file "$file" &
done
wait

# Using xargs
find . -name "*.txt" | xargs -P 4 -I {} process_file {}

# Using GNU parallel
parallel process_file ::: *.txt
```
"""
        return ScrapedDocument(
            id=self._generate_id("scripting-patterns"),
            url="synthetic://shell-scripting",
            title="Shell Scripting Best Practices",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["bash", "shell", "scripting", "best-practices"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _awk_guide(self) -> ScrapedDocument:
        """awk guide."""
        content = """# AWK Text Processing Guide

## Basic Syntax

```bash
awk 'pattern { action }' file
awk -F: 'pattern { action }' file    # Custom delimiter
```

## Print Columns

```bash
# Print specific columns
awk '{print $1}' file                 # First column
awk '{print $1, $3}' file             # First and third
awk '{print $NF}' file                # Last column
awk '{print $(NF-1)}' file            # Second to last

# With custom delimiter
awk -F: '{print $1}' /etc/passwd      # Username
awk -F, '{print $2}' file.csv         # CSV second column

# Output delimiter
awk -F: -v OFS="," '{print $1, $3}' /etc/passwd
```

## Patterns

```bash
# Match pattern
awk '/error/' file                    # Lines with "error"
awk '!/error/' file                   # Lines without "error"
awk '/start/,/end/' file              # Range between patterns

# Comparison
awk '$3 > 100' file                   # Third column > 100
awk '$1 == "admin"' file              # First column is "admin"
awk 'NR > 1' file                     # Skip header

# Combine patterns
awk '/error/ && $3 > 5' file
awk '/error/ || /warning/' file
```

## Built-in Variables

```bash
NR      # Current line number
NF      # Number of fields
FS      # Field separator (input)
OFS     # Output field separator
RS      # Record separator (input)
ORS     # Output record separator
FILENAME # Current filename
```

## Actions

```bash
# Multiple actions
awk '{print $1; print $2}' file

# Calculations
awk '{sum += $1} END {print sum}' file
awk '{print $1 * $2}' file

# String concatenation
awk '{print $1 "-" $2}' file

# printf formatting
awk '{printf "%-10s %5d\\n", $1, $2}' file
```

## BEGIN and END

```bash
# Header and footer
awk 'BEGIN {print "Header"} {print} END {print "Footer"}' file

# Initialize variables
awk 'BEGIN {sum=0} {sum+=$1} END {print "Total:", sum}' file

# Set field separator in BEGIN
awk 'BEGIN {FS=":"} {print $1}' /etc/passwd
```

## Common Recipes

```bash
# Sum a column
awk '{sum += $1} END {print sum}' file

# Average
awk '{sum += $1; count++} END {print sum/count}' file

# Count lines matching pattern
awk '/error/ {count++} END {print count}' file

# Remove duplicates (keep order)
awk '!seen[$0]++' file

# Print lines between patterns
awk '/START/,/END/' file

# Number lines
awk '{print NR": "$0}' file

# Skip blank lines
awk 'NF' file

# Print line length
awk '{print length, $0}' file

# Swap columns
awk '{print $2, $1}' file

# Replace field
awk '{$2="new"; print}' file

# Group by column
awk '{count[$1]++} END {for (k in count) print k, count[k]}' file

# Max value
awk 'BEGIN {max=0} $1>max {max=$1} END {print max}' file
```

## Conditionals and Loops

```bash
# if-else
awk '{if ($1 > 100) print "big"; else print "small"}' file

# Ternary
awk '{print ($1 > 100 ? "big" : "small")}' file

# for loop
awk '{for (i=1; i<=NF; i++) print $i}' file

# while loop
awk '{i=1; while (i<=NF) {print $i; i++}}' file
```

## Regex in AWK

```bash
# Match field against regex
awk '$1 ~ /^[0-9]+$/' file            # First field is numeric
awk '$1 !~ /^#/' file                 # Not a comment

# Case insensitive
awk 'tolower($0) ~ /error/' file
```
"""
        return ScrapedDocument(
            id=self._generate_id("awk-guide"),
            url="https://www.gnu.org/software/gawk/manual/",
            title="AWK Text Processing Guide",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["awk", "text-processing", "linux", "shell"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _sed_guide(self) -> ScrapedDocument:
        """sed guide."""
        content = """# sed Stream Editor Guide

## Basic Syntax

```bash
sed 's/old/new/' file         # Substitute first occurrence
sed 's/old/new/g' file        # Substitute all occurrences
sed -i 's/old/new/g' file     # Edit in place
sed -i.bak 's/old/new/g' file # Backup before edit
```

## Substitution Flags

```bash
s/old/new/g     # Global (all occurrences)
s/old/new/i     # Case insensitive
s/old/new/2     # Only 2nd occurrence
s/old/new/p     # Print if matched (use with -n)
s/old/new/w file # Write matches to file
```

## Delimiters

```bash
# Use any character as delimiter
sed 's|/path/old|/path/new|g' file
sed 's#old#new#g' file
sed 's@old@new@g' file
```

## Address Ranges

```bash
# Line numbers
sed '5s/old/new/' file        # Only line 5
sed '1,10s/old/new/' file     # Lines 1-10
sed '10,$s/old/new/' file     # Line 10 to end

# Patterns
sed '/pattern/s/old/new/' file          # Lines matching pattern
sed '/start/,/end/s/old/new/' file      # Range between patterns

# Negation
sed '5!s/old/new/' file       # All except line 5
sed '/pattern/!s/old/new/' file         # Lines NOT matching
```

## Common Commands

```bash
# Delete lines
sed 'd' file                  # Delete all
sed '5d' file                 # Delete line 5
sed '1,5d' file               # Delete lines 1-5
sed '/pattern/d' file         # Delete matching lines
sed '/^$/d' file              # Delete blank lines
sed '/^#/d' file              # Delete comments

# Print lines
sed -n '5p' file              # Print line 5
sed -n '1,10p' file           # Print lines 1-10
sed -n '/pattern/p' file      # Print matching lines

# Insert/Append
sed '3i New line' file        # Insert before line 3
sed '3a New line' file        # Append after line 3
sed '/pattern/i New line' file

# Change entire line
sed '3c Replacement line' file
sed '/pattern/c Replacement' file
```

## Capture Groups

```bash
# Backreferences
sed 's/\\(word\\)/[\\1]/' file              # Wrap word in brackets
sed 's/\\([0-9]*\\)/Number: \\1/' file      # Capture numbers

# Extended regex (-E or -r)
sed -E 's/(word)/[\\1]/' file
sed -E 's/([0-9]+)/Number: \\1/' file

# Multiple groups
sed -E 's/([a-z]+) ([a-z]+)/\\2 \\1/' file  # Swap words
```

## Multiple Commands

```bash
# Semicolon
sed 's/a/A/; s/b/B/' file

# -e flag
sed -e 's/a/A/' -e 's/b/B/' file

# Script file
sed -f script.sed file
```

## Common Recipes

```bash
# Remove leading whitespace
sed 's/^[ \\t]*//' file

# Remove trailing whitespace
sed 's/[ \\t]*$//' file

# Remove blank lines
sed '/^$/d' file

# Remove comments
sed '/^#/d' file
sed 's/#.*//' file            # Remove inline comments

# Print specific line
sed -n '10p' file

# Print last line
sed -n '$p' file

# Add line numbers
sed = file | sed 'N;s/\\n/\\t/'

# Duplicate lines
sed 'p' file

# Join lines
sed 'N;s/\\n/ /' file

# Convert to uppercase
sed 's/.*/\\U&/' file

# Convert to lowercase
sed 's/.*/\\L&/' file

# Remove HTML tags
sed 's/<[^>]*>//g' file

# Extract email addresses
sed -n 's/.*\\([a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]*\\.[a-zA-Z]*\\).*/\\1/p' file
```

## Hold Space

```bash
# Hold space for advanced operations
sed 'H;1h;$!d;x;s/\\n/,/g' file    # Join lines with comma

# Reverse file
sed -n '1!G;h;$p' file
```
"""
        return ScrapedDocument(
            id=self._generate_id("sed-guide"),
            url="https://www.gnu.org/software/sed/manual/",
            title="sed Stream Editor Guide",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["sed", "text-processing", "linux", "shell"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _grep_guide(self) -> ScrapedDocument:
        """grep guide."""
        content = """# grep Search Guide

## Basic Usage

```bash
grep 'pattern' file
grep 'pattern' file1 file2
grep 'pattern' *.txt
cat file | grep 'pattern'
```

## Common Options

```bash
-i          # Case insensitive
-v          # Invert match (lines NOT matching)
-c          # Count matches
-n          # Show line numbers
-l          # Show only filenames
-L          # Show files NOT matching
-r, -R      # Recursive
-w          # Match whole words
-x          # Match whole lines
-o          # Show only matched part
-A 3        # Show 3 lines after
-B 3        # Show 3 lines before
-C 3        # Show 3 lines before and after
-q          # Quiet (exit status only)
-E          # Extended regex (egrep)
-P          # Perl regex
-F          # Fixed strings (fgrep)
```

## Pattern Matching

```bash
# Basic patterns
grep 'error' file
grep 'Error' file

# Case insensitive
grep -i 'error' file

# Whole word
grep -w 'error' file          # Won't match "errors"

# Whole line
grep -x 'exact line' file

# Multiple patterns
grep -e 'error' -e 'warning' file
grep 'error\\|warning' file
grep -E 'error|warning' file

# From file
grep -f patterns.txt file
```

## Regular Expressions

```bash
# Basic regex
grep '^start' file            # Lines starting with
grep 'end$' file              # Lines ending with
grep '^$' file                # Empty lines
grep '.' file                 # Any character
grep 'a*b' file               # Zero or more 'a' before 'b'
grep 'a\\+b' file             # One or more 'a' before 'b'
grep 'a\\?b' file             # Zero or one 'a' before 'b'
grep '[abc]' file             # Any of a, b, c
grep '[^abc]' file            # Not a, b, c
grep '[a-z]' file             # Range

# Extended regex (-E)
grep -E 'a+b' file            # One or more
grep -E 'a?b' file            # Zero or one
grep -E 'a{3}' file           # Exactly 3 'a's
grep -E 'a{3,5}' file         # 3 to 5 'a's
grep -E '(ab)+' file          # Grouping
grep -E 'cat|dog' file        # Or
```

## Recursive Search

```bash
# Search directories
grep -r 'pattern' /path/
grep -R 'pattern' /path/      # Follow symlinks

# Include/exclude files
grep -r --include='*.py' 'pattern' .
grep -r --exclude='*.log' 'pattern' .
grep -r --exclude-dir='.git' 'pattern' .
```

## Context

```bash
# Lines around match
grep -A 3 'pattern' file      # 3 lines after
grep -B 3 'pattern' file      # 3 lines before
grep -C 3 'pattern' file      # 3 lines before and after
```

## Common Recipes

```bash
# Count occurrences
grep -c 'pattern' file

# List files with matches
grep -l 'pattern' *.txt

# List files without matches
grep -L 'pattern' *.txt

# Show only matched text
grep -o 'pattern' file

# Find IP addresses
grep -oE '[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}' file

# Find email addresses
grep -oE '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}' file

# Find URLs
grep -oE 'https?://[^[:space:]]+' file

# Count unique matches
grep -oh 'pattern' file | sort | uniq -c

# Search compressed files
zgrep 'pattern' file.gz

# Search in command output
ps aux | grep nginx
dmesg | grep -i error
```

## Exit Status

```bash
# 0 = match found, 1 = no match, 2 = error
grep -q 'pattern' file && echo "Found"
if grep -q 'pattern' file; then
    echo "Found"
fi
```

## Performance Tips

```bash
# Fixed string (faster than regex)
grep -F 'literal' file
fgrep 'literal' file

# Stop at first match
grep -m 1 'pattern' file

# Parallel grep (ripgrep)
rg 'pattern' .
```
"""
        return ScrapedDocument(
            id=self._generate_id("grep-guide"),
            url="https://www.gnu.org/software/grep/manual/",
            title="grep Search Guide",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["grep", "search", "regex", "linux", "shell"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _find_xargs_guide(self) -> ScrapedDocument:
        """find and xargs guide."""
        content = """# find and xargs Guide

## find Basics

```bash
find /path -name "pattern"
find . -name "*.txt"
find / -name "file" 2>/dev/null   # Suppress errors
```

## Find by Type

```bash
find . -type f                    # Files only
find . -type d                    # Directories only
find . -type l                    # Symbolic links
find . -type f -name "*.txt"      # Combine
```

## Find by Name

```bash
find . -name "*.txt"              # Case sensitive
find . -iname "*.txt"             # Case insensitive
find . -name "*.txt" -o -name "*.md"  # OR
find . -not -name "*.txt"         # NOT
find . ! -name "*.txt"            # NOT (alternative)
```

## Find by Time

```bash
# Modified time
find . -mtime -7                  # Modified < 7 days ago
find . -mtime +30                 # Modified > 30 days ago
find . -mtime 1                   # Modified exactly 1 day ago

# Access time
find . -atime -7                  # Accessed < 7 days ago

# Changed time (metadata)
find . -ctime -7

# Minutes instead of days
find . -mmin -60                  # Modified < 60 minutes ago

# Newer than file
find . -newer reference.txt
```

## Find by Size

```bash
find . -size +100M                # Larger than 100MB
find . -size -1k                  # Smaller than 1KB
find . -size 0                    # Empty files
find . -empty                     # Empty files and directories

# Size units: c (bytes), k (KB), M (MB), G (GB)
```

## Find by Permissions

```bash
find . -perm 644                  # Exact match
find . -perm -644                 # At least these
find . -perm /644                 # Any of these

find . -perm -u+x                 # User executable
find . -executable                # Executable by current user
find . -writable                  # Writable by current user
```

## Find by Owner

```bash
find . -user username
find . -group groupname
find . -uid 1000
find . -gid 1000
find . -nouser                    # No owner
find . -nogroup                   # No group
```

## Find and Execute

```bash
# -exec (one at a time)
find . -name "*.txt" -exec cat {} \\;
find . -name "*.tmp" -exec rm {} \\;

# -exec with + (batch, like xargs)
find . -name "*.txt" -exec cat {} +

# -execdir (run in file's directory)
find . -name "*.txt" -execdir cat {} \\;

# -ok (prompt before each)
find . -name "*.tmp" -ok rm {} \\;

# Delete directly
find . -name "*.tmp" -delete
```

## xargs

```bash
# Basic usage
find . -name "*.txt" | xargs cat
echo "file1 file2" | xargs rm

# With -I for placeholder
find . -name "*.txt" | xargs -I {} cp {} /backup/

# Null-separated (safe for spaces)
find . -name "*.txt" -print0 | xargs -0 cat

# Limit arguments per command
find . -name "*.txt" | xargs -n 1 cat

# Parallel execution
find . -name "*.txt" | xargs -P 4 -I {} process {}

# Confirm before each
find . -name "*.tmp" | xargs -p rm

# Handle empty input
find . -name "*.missing" | xargs --no-run-if-empty cat
find . -name "*.missing" | xargs -r cat  # Short form
```

## Common Recipes

```bash
# Delete old files
find /tmp -type f -mtime +7 -delete

# Find large files
find / -type f -size +100M 2>/dev/null

# Find and archive
find . -name "*.log" | tar -cvf logs.tar -T -

# Change permissions
find . -type f -exec chmod 644 {} +
find . -type d -exec chmod 755 {} +

# Find duplicates by name
find . -type f -name "*.txt" | sort | uniq -d

# Count files by extension
find . -type f | sed 's/.*\\.//' | sort | uniq -c | sort -rn

# Find broken symlinks
find . -xtype l

# Find files not matching pattern
find . -type f ! -name "*.txt"

# Combine with grep
find . -name "*.py" -exec grep -l "import os" {} +

# Safe delete with confirmation
find . -name "*.tmp" -print0 | xargs -0 -p rm

# Process in parallel
find . -name "*.jpg" -print0 | xargs -0 -P 4 -I {} convert {} -resize 50% small_{}
```
"""
        return ScrapedDocument(
            id=self._generate_id("find-xargs"),
            url="https://www.gnu.org/software/findutils/manual/",
            title="find and xargs Guide",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["find", "xargs", "linux", "shell", "files"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "reference", "priority": "high"}
        )
    
    def _process_guide(self) -> ScrapedDocument:
        """Process management guide."""
        content = """# Linux Process Management Guide

## View Processes

```bash
# ps command
ps                        # Current terminal processes
ps aux                    # All processes, user-oriented
ps -ef                    # All processes, full format
ps aux --sort=-%mem       # Sort by memory
ps aux --sort=-%cpu       # Sort by CPU
ps -u username            # Processes by user

# top/htop
top
htop                      # Interactive, prettier

# pgrep
pgrep nginx               # PIDs matching name
pgrep -u root             # By user
pgrep -a nginx            # With full command
```

## Process Information

```bash
# Process tree
pstree
pstree -p                 # With PIDs
pstree -u                 # With usernames

# Process details
cat /proc/PID/status
cat /proc/PID/cmdline
ls -la /proc/PID/fd       # Open files

# Resources
cat /proc/PID/limits
cat /proc/PID/stat
```

## Signals

```bash
# Send signal
kill PID                  # SIGTERM (15) - graceful
kill -9 PID               # SIGKILL (9) - force
kill -HUP PID             # SIGHUP (1) - reload config
kill -STOP PID            # SIGSTOP (19) - pause
kill -CONT PID            # SIGCONT (18) - resume

# By name
pkill nginx
pkill -u username
killall nginx

# List signals
kill -l
```

## Common Signals

| Signal | Number | Description |
|--------|--------|-------------|
| SIGHUP | 1 | Reload configuration |
| SIGINT | 2 | Interrupt (Ctrl+C) |
| SIGQUIT | 3 | Quit with core dump |
| SIGKILL | 9 | Force kill (can't catch) |
| SIGTERM | 15 | Graceful termination |
| SIGSTOP | 19 | Pause (can't catch) |
| SIGCONT | 18 | Resume |
| SIGUSR1 | 10 | User-defined |
| SIGUSR2 | 12 | User-defined |

## Background Jobs

```bash
# Run in background
command &

# Move to background
Ctrl+Z                    # Suspend
bg                        # Continue in background

# Bring to foreground
fg
fg %1                     # Specific job

# List jobs
jobs
jobs -l                   # With PIDs

# Disown (survive logout)
disown
disown %1
nohup command &           # Or use nohup

# Keep running after logout
nohup command > output.log 2>&1 &
```

## Process Priority

```bash
# View priority
ps -eo pid,ni,comm
top                       # NI column

# Start with priority
nice -n 10 command        # Lower priority (10)
nice -n -10 command       # Higher priority (root only)

# Change running process
renice 10 -p PID
renice -10 -p PID         # Root only
renice 10 -u username     # All user's processes
```

## Resource Limits

```bash
# View limits
ulimit -a

# Set limits (current session)
ulimit -n 65535           # Open files
ulimit -u 4096            # Max processes
ulimit -v unlimited       # Virtual memory

# Permanent limits
# /etc/security/limits.conf
# username soft nofile 65535
# username hard nofile 65535
```

## Monitoring

```bash
# Real-time process monitoring
top
htop
atop

# System load
uptime
cat /proc/loadavg

# Memory
free -h
vmstat 1

# CPU
mpstat 1
sar -u 1 5

# I/O
iotop
pidstat -d 1
```

## Control Groups (cgroups)

```bash
# View cgroups
cat /proc/PID/cgroup

# List cgroup controllers
cat /sys/fs/cgroup/cgroup.controllers

# Limit memory with systemd
systemd-run --scope -p MemoryMax=500M command

# CPU limit
systemd-run --scope -p CPUQuota=50% command
```
"""
        return ScrapedDocument(
            id=self._generate_id("process-guide"),
            url="synthetic://process-management",
            title="Linux Process Management Guide",
            content=content,
            source=self.get_source_name(),
            category="system_admin",
            tags=["linux", "process", "ps", "kill", "jobs"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "guide", "priority": "high"}
        )
    
    def _oneliners_guide(self) -> ScrapedDocument:
        """Common one-liners guide."""
        content = """# Linux One-Liners Cheat Sheet

## File Operations

```bash
# Find and replace in files
find . -name "*.txt" -exec sed -i 's/old/new/g' {} +

# Batch rename files
for f in *.txt; do mv "$f" "${f%.txt}.md"; done

# Delete empty files
find . -type f -empty -delete

# Delete empty directories
find . -type d -empty -delete

# Copy preserving structure
rsync -av --include='*.txt' --include='*/' --exclude='*' src/ dest/

# Compare directories
diff -rq dir1 dir2

# Count files by type
find . -type f | sed 's/.*\\.//' | sort | uniq -c | sort -rn

# Find largest files
du -ah . | sort -rh | head -20

# Find largest directories
du -h --max-depth=1 | sort -rh

# Sum file sizes
find . -type f -name "*.log" -exec du -cb {} + | tail -1
```

## Text Processing

```bash
# Sort and unique
sort file | uniq
sort -u file

# Count occurrences
sort file | uniq -c | sort -rn

# Extract column
awk '{print $2}' file
cut -d',' -f2 file.csv

# Remove duplicates (keep order)
awk '!seen[$0]++' file

# Remove blank lines
grep -v '^$' file
sed '/^$/d' file

# Join lines
paste -sd',' file
tr '\\n' ',' < file

# Split into chunks
split -l 1000 file.txt chunk_

# Random sample
shuf -n 10 file
sort -R file | head -10

# Diff two sorted files
comm -23 file1 file2       # Only in file1
comm -13 file1 file2       # Only in file2
comm -12 file1 file2       # In both
```

## System Information

```bash
# Disk usage summary
df -h | grep -v tmpfs

# Memory usage
free -h

# Top memory processes
ps aux --sort=-%mem | head -10

# Top CPU processes
ps aux --sort=-%cpu | head -10

# Open ports
ss -tlnp
netstat -tlnp

# Who's logged in
w
who

# System uptime
uptime

# Kernel version
uname -r

# OS info
cat /etc/os-release
```

## Network

```bash
# Download file
wget -O output.file URL
curl -o output.file URL

# Test connectivity
ping -c 3 host

# Check open ports on host
nmap -p 1-1000 host

# Get public IP
curl ifconfig.me
curl icanhazip.com

# DNS lookup
dig +short domain.com
host domain.com

# Monitor network traffic
sudo tcpdump -i eth0 -n

# HTTP request
curl -X POST -H "Content-Type: application/json" -d '{"key":"value"}' URL
```

## Log Analysis

```bash
# Follow log
tail -f /var/log/syslog

# Last N lines
tail -100 /var/log/syslog

# Search logs
grep -r "error" /var/log/

# Count errors by hour
grep "error" log | cut -d' ' -f1-2 | uniq -c

# Top IP addresses (Apache)
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head

# Response codes count
awk '{print $9}' access.log | sort | uniq -c | sort -rn

# Requests per second
awk '{print $4}' access.log | cut -d: -f1-3 | sort | uniq -c

# Slow requests
awk '$NF > 5 {print}' access.log
```

## Security

```bash
# Find SUID files
find / -perm -4000 2>/dev/null

# Find world-writable files
find / -perm -0002 -type f 2>/dev/null

# Check for failed logins
grep "Failed password" /var/log/auth.log

# List users
cat /etc/passwd | cut -d: -f1

# Last logins
last
lastlog

# Check listening services
sudo lsof -i -P -n | grep LISTEN
```

## JSON Processing (jq)

```bash
# Pretty print
cat file.json | jq .

# Extract field
cat file.json | jq '.name'
cat file.json | jq '.users[0].name'

# Filter
cat file.json | jq '.users[] | select(.age > 30)'

# Transform
cat file.json | jq '{name: .name, age: .age}'
```

## Quick Utilities

```bash
# Generate password
openssl rand -base64 32

# Calculate hash
echo -n "text" | md5sum
sha256sum file

# Base64 encode/decode
echo "text" | base64
echo "dGV4dA==" | base64 -d

# URL encode/decode
python3 -c "import urllib.parse; print(urllib.parse.quote('hello world'))"

# Date formatting
date +%Y-%m-%d
date +%s                  # Unix timestamp
date -d @1234567890       # From timestamp

# Quick HTTP server
python3 -m http.server 8000

# Watch command output
watch -n 1 'ps aux | grep nginx'
```
"""
        return ScrapedDocument(
            id=self._generate_id("oneliners"),
            url="synthetic://linux-oneliners",
            title="Linux One-Liners Cheat Sheet",
            content=content,
            source=self.get_source_name(),
            category="shell",
            tags=["linux", "bash", "oneliners", "cheatsheet"],
            scraped_at=datetime.utcnow().isoformat(),
            metadata={"type": "cheatsheet", "priority": "high"}
        )
    
    def _generate_id(self, name: str) -> str:
        """Generate document ID."""
        import hashlib
        return hashlib.md5(f"shell-docs:{name}".encode()).hexdigest()[:16]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate shell documentation")
    parser.add_argument("--output-dir", default="data/linux/shell-docs")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    config = ScraperConfig(output_dir=Path(args.output_dir))
    scraper = ShellDocsScraper(config)
    
    docs = scraper.scrape()
    scraper.save_documents(docs, "shell_docs.jsonl")
