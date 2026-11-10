#!/usr/bin/env bash
#
# Package each skill under skills/ into a distributable .skill bundle.
#
# A .skill file is just a zip archive whose single top-level directory is the
# skill name, containing SKILL.md plus any bundled resources.
#
# Usage:
#   ./build.sh                        build every skill into dist/
#   ./build.sh engineering-playbook   build only the named skill(s)
#   ./build.sh --check                validate only, write nothing
#   ./build.sh --link                 symlink skills/* into ~/.claude/skills
#   ./build.sh --clean                remove dist/
#   ./build.sh --agents               (re)generate AGENTS.md for non-Claude agents
#   ./build.sh --install DIR          copy skills into DIR/.claude/skills (commit these)
#   ./build.sh --out DIR              write bundles somewhere other than dist/

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$ROOT/skills"
OUT_DIR="$ROOT/dist"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"

MAX_NAME_LEN=64
# Anthropic's skill authoring guidance: keep SKILL.md bodies short, and give any
# reference file long enough to be read in parts a table of contents up front.
# See refs/agent-skills-best-practices.md.
MAX_SKILL_BODY_LINES=500
TOC_REQUIRED_OVER_LINES=100
MAX_DESCRIPTION_LEN=1024
SHORT_DESCRIPTION_LEN=60

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; DIM=''; RESET=''
fi

die() { printf '%serror%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }
ok()   { printf '%sok%s   %-32s %s%s%s\n'   "$GREEN"  "$RESET" "$1" "$DIM" "$2" "$RESET"; }
warn() { printf '%swarn%s %-32s %s%s%s\n'   "$YELLOW" "$RESET" "$1" "$DIM" "$2" "$RESET"; }
fail() { printf '%sfail%s %-32s %s\n'       "$RED"    "$RESET" "$1" "$2" >&2; }

# Prints the header comment block (everything after the shebang up to the first
# non-comment line) as the help text.
usage() {
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}" \
    | sed '/./,$!d'
}

# --- argument parsing -------------------------------------------------------

MODE=build
INSTALL_DIR=""
NAMES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE=check ;;
    --link)  MODE=link ;;
    --agents) MODE=agents ;;
    --install)
      [[ $# -ge 2 ]] || die "--install needs a project directory"
      MODE=install; INSTALL_DIR="$2"; shift ;;
    --clean) MODE=clean ;;
    --out)   [[ $# -ge 2 ]] || die "--out needs a directory"; OUT_DIR="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)      die "unknown option: $1" ;;
    *)       NAMES+=("$1") ;;
  esac
  shift
done

# --- frontmatter parsing ----------------------------------------------------

# Reads a SKILL.md on stdin, prints "<key>\t<value>" for name and description,
# or "ERROR\t<message>" (exit 1) if the frontmatter block is unparseable.
# Only the subset a SKILL.md needs: `key: value` pairs, values optionally
# quoted, with folded continuation lines for long descriptions.
read_frontmatter() {
  awk '
    { sub(/\r$/, "") }
    NR == 1 {
      if ($0 !~ /^---[ \t]*$/) { err = "SKILL.md must start with a `---` frontmatter block"; exit }
      next
    }
    !closed && $0 ~ /^---[ \t]*$/ { closed = 1; exit }
    !closed {
      if ($0 ~ /^[ \t]*$/) next
      if ($0 ~ /^[A-Za-z0-9_-]+:/) {
        i = index($0, ":")
        key = substr($0, 1, i - 1)
        val = substr($0, i + 1)
        gsub(/^[ \t]+|[ \t]+$/, "", val)
        sub(/^["'"'"']/, "", val); sub(/["'"'"']$/, "", val)
        vals[key] = val
      } else if (key != "") {
        line = $0
        gsub(/^[ \t]+|[ \t]+$/, "", line)
        vals[key] = vals[key] " " line
      } else {
        err = "cannot parse frontmatter line: " $0; exit
      }
    }
    END {
      if (err)     { print "ERROR\t" err; exit 1 }
      if (!closed) { print "ERROR\tfrontmatter block is never closed with `---`"; exit 1 }
      print "name\t"        vals["name"]
      print "description\t" vals["description"]
    }
  '
}

# Sets NAME and DESCRIPTION, or returns 1 with REASON set.
validate() {
  local skill_dir="$1" skill_md="$1/SKILL.md" line key value
  NAME=''; DESCRIPTION=''; REASON=''

  if [[ ! -f "$skill_md" ]]; then
    REASON="no SKILL.md in the skill directory"; return 1
  fi

  while IFS=$'\t' read -r key value; do
    case "$key" in
      ERROR)       REASON="$value"; return 1 ;;
      name)        NAME="$value" ;;
      description) DESCRIPTION="$value" ;;
    esac
  done < <(read_frontmatter < "$skill_md")

  local dir_name; dir_name="$(basename "$skill_dir")"
  if [[ -z "$NAME" ]]; then
    REASON="frontmatter is missing \`name\`"; return 1
  fi
  if [[ "$NAME" != "$dir_name" ]]; then
    REASON="frontmatter name '$NAME' does not match directory '$dir_name'"; return 1
  fi
  if [[ ! "$NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    REASON="name '$NAME' must be lowercase letters/digits separated by hyphens"; return 1
  fi
  if (( ${#NAME} > MAX_NAME_LEN )); then
    REASON="name is ${#NAME} chars, max is $MAX_NAME_LEN"; return 1
  fi
  if [[ -z "$DESCRIPTION" ]]; then
    REASON="frontmatter is missing \`description\` (this is what routes work to the skill)"; return 1
  fi
  if (( ${#DESCRIPTION} > MAX_DESCRIPTION_LEN )); then
    REASON="description is ${#DESCRIPTION} chars, max is $MAX_DESCRIPTION_LEN"; return 1
  fi
  return 0
}

# --- file collection --------------------------------------------------------

# Prints the shippable files of a skill, one per line, relative to skills/
# (so each path already starts with the skill name, which is the archive root).
collect_files() {
  local name="$1"
  ( cd "$SKILLS_DIR" && find "$name" \
      \( -name '.git' -o -name '__pycache__' -o -name 'node_modules' -o -name '.venv' \
         -o -name '.ipynb_checkpoints' -o -name '.pytest_cache' -o -name '.ruff_cache' \) -prune -o \
      -type f \
      ! -name '.DS_Store' ! -name 'Thumbs.db' ! -name '.gitignore' ! -name '.gitkeep' \
      ! -name '*.pyc' ! -name '*.pyo' ! -name '*.swp' ! -name '*.tmp' \
      ! -name '*.bak' ! -name '*.orig' \
      -print ) | LC_ALL=C sort
}

# Warnings only — these are authoring guidelines, not bundle-breaking errors.
# Prints one line per issue; the caller decides how loudly to report them.
lint_skill() {
  local name="$1" skill_dir="$SKILLS_DIR/$1" body_lines file rel lines

  # SKILL.md body (everything after the closing frontmatter ---)
  body_lines="$(awk 'NR > 1 && /^---[ \t]*$/ { found = 1; next } found { n++ } END { print n + 0 }' \
                  "$skill_dir/SKILL.md")"
  if (( body_lines >= MAX_SKILL_BODY_LINES )); then
    echo "SKILL.md body is $body_lines lines (guideline: under $MAX_SKILL_BODY_LINES) — split into references/"
  fi

  while IFS= read -r file; do
    rel="${file#"$name"/}"
    [[ "$rel" == "SKILL.md" || "$rel" != *.md ]] && continue
    lines="$(wc -l < "$skill_dir/$rel" | tr -d ' ')"
    if (( lines > TOC_REQUIRED_OVER_LINES )) && ! grep -qE '^## (목차|Contents)' "$skill_dir/$rel"; then
      echo "$rel is $lines lines with no table of contents (needed over $TOC_REQUIRED_OVER_LINES)"
    fi
    if ! grep -q "\`$rel\`" "$skill_dir/SKILL.md"; then
      echo "$rel is never mentioned in SKILL.md — it will not be discovered"
    fi
  done < <(collect_files "$name")
}

# --- zipping ----------------------------------------------------------------

# Zips the newline-separated file list in $2 (paths relative to skills/) into $1.
zip_bundle() {
  local bundle="$1" list_file="$2"
  if command -v zip >/dev/null 2>&1; then
    ( cd "$SKILLS_DIR" && zip -q -X "$bundle" -@ < "$list_file" )
  elif command -v python3 >/dev/null 2>&1; then
    # No zip(1) on this box; python3's stdlib writes the same archive.
    python3 - "$SKILLS_DIR" "$bundle" "$list_file" <<'PY'
import sys, zipfile
base, bundle, list_file = sys.argv[1:4]
with open(list_file, encoding="utf-8") as handle:
    names = [line.rstrip("\n") for line in handle if line.strip()]
with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(f"{base}/{name}", arcname=name)
PY
  else
    die "need either \`zip\` or \`python3\` to write a bundle (try: sudo apt install zip)"
  fi
}

human_size() {
  local bytes="$1"
  if (( bytes < 1048576 )); then
    awk -v b="$bytes" 'BEGIN { printf "%.1f KB", b / 1024 }'
  else
    awk -v b="$bytes" 'BEGIN { printf "%.1f MB", b / 1048576 }'
  fi
}

build_skill() {
  local name="$1" list_file bundle staging count
  list_file="$(mktemp)"
  collect_files "$name" > "$list_file"
  count="$(wc -l < "$list_file" | tr -d ' ')"
  if (( count == 0 )); then
    rm -f "$list_file"
    REASON="skill directory contains no shippable files"; return 1
  fi

  mkdir -p "$OUT_DIR" || { rm -f "$list_file"; REASON="cannot create $OUT_DIR"; return 1; }
  bundle="$OUT_DIR/$name.skill"
  staging="$bundle.tmp"

  # Write to a temp path first so a failure never leaves a half-written bundle.
  rm -f "$staging"
  if ! zip_bundle "$staging" "$list_file"; then
    rm -f "$staging" "$list_file"; REASON="failed to write the zip archive"; return 1
  fi
  rm -f "$list_file"
  mv -f "$staging" "$bundle" || { REASON="cannot move bundle into place"; return 1; }

  NOTE="${bundle#"$ROOT"/}  $(human_size "$(wc -c < "$bundle" | tr -d ' ')")"
  return 0
}

# Symlink a skill into ~/.claude/skills so local edits are live immediately.
link_skill() {
  local name="$1" src="$SKILLS_DIR/$1" target="$CLAUDE_SKILLS_DIR/$1"
  mkdir -p "$CLAUDE_SKILLS_DIR" || { REASON="cannot create $CLAUDE_SKILLS_DIR"; return 1; }
  if [[ -L "$target" ]]; then
    if [[ "$(cd "$(dirname "$target")" && readlink -f "$target")" == "$src" ]]; then
      NOTE="already linked"; return 0
    fi
    rm -f "$target"
  elif [[ -e "$target" ]]; then
    REASON="$target exists and is not a symlink — move it aside first"; return 1
  fi
  ln -s "$src" "$target" || { REASON="cannot create symlink at $target"; return 1; }
  NOTE="linked -> $target"
  return 0
}

# Copies a skill into <project>/.claude/skills/<name>/ as real files.
# Project-level skills are meant to be committed, so teammates and CI get them —
# a symlink would not survive a clone. For your own machine use --link instead,
# which points ~/.claude/skills at this repo and leaves no copies to drift.
install_skill() {
  local name="$1" src="$SKILLS_DIR/$1" dest="$INSTALL_DIR/.claude/skills/$1" file

  if [[ ! -d "$INSTALL_DIR" ]]; then
    REASON="$INSTALL_DIR does not exist"; return 1
  fi
  if [[ -L "$dest" ]]; then
    REASON="$dest is a symlink — remove it first, or use --link for personal scope"; return 1
  fi

  # Replace wholesale so files deleted from the source do not linger in the copy.
  rm -rf "$dest"
  mkdir -p "$dest" || { REASON="cannot create $dest"; return 1; }

  while IFS= read -r file; do
    mkdir -p "$dest/$(dirname "${file#"$name"/}")"
    cp "$SKILLS_DIR/$file" "$dest/${file#"$name"/}" || { REASON="cannot copy $file"; return 1; }
  done < <(collect_files "$name")

  NOTE="$dest"
  return 0
}

# --- AGENTS.md ---------------------------------------------------------------

# Writes AGENTS.md at the repo root: an entry point for agent tools that read the
# AGENTS.md convention (Codex, Cursor, Zed, ...) rather than Claude's SKILL.md.
# It only points at the skills — the instructions themselves stay in plain markdown
# under skills/, so there is one copy to maintain.
write_agents_md() {
  local out="$ROOT/AGENTS.md" name file

  {
    cat <<'MD'
# AGENTS.md

<!-- Generated by ./build.sh --agents. Edit skills/*/SKILL.md, not this file. -->

This repository holds reusable agent skills. A skill is a directory of plain markdown:
`SKILL.md` is the routing index, and `references/` holds the detail.

**How to use one:** when the task matches a skill's description below, read that skill's
`SKILL.md` first, then open only the reference files its routing table points you to.
Do not read every reference file up front — that is what the routing table is for.

A skill whose description says it always applies is a standing instruction: apply it to any
matching work without waiting to be asked for it by name.

## Skills

MD

    for name in "${SELECTED[@]}"; do
      validate "$SKILLS_DIR/$name" || continue
      printf '### %s\n\n' "$name"
      printf '`skills/%s/SKILL.md`\n\n' "$name"
      printf '%s\n\n' "$DESCRIPTION"
      printf 'Bundled files:\n\n'
      while IFS= read -r file; do
        [[ "$file" == "$name/SKILL.md" ]] && continue
        printf -- '- `skills/%s`\n' "$file"
      done < <(collect_files "$name")
      printf '\n'
    done
  } > "$out"

  NOTE="${out#"$ROOT"/}  $(wc -l < "$out" | tr -d ' ') lines"
}

# --- main -------------------------------------------------------------------

if [[ "$MODE" == clean ]]; then
  if [[ -d "$OUT_DIR" ]]; then
    rm -rf "$OUT_DIR"
    printf '%sremoved%s %s/\n' "$GREEN" "$RESET" "${OUT_DIR#"$ROOT"/}"
  else
    printf '%snothing to clean%s\n' "$DIM" "$RESET"
  fi
  exit 0
fi

[[ -d "$SKILLS_DIR" ]] || die "no skills/ directory at $SKILLS_DIR"

ALL=()
while IFS= read -r dir; do
  ALL+=("$(basename "$dir")")
done < <(find "$SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d ! -name '.*' | LC_ALL=C sort)

SELECTED=()
if (( ${#NAMES[@]} > 0 )); then
  for name in "${NAMES[@]}"; do
    found=0
    for candidate in ${ALL[@]+"${ALL[@]}"}; do
      [[ "$candidate" == "$name" ]] && found=1 && break
    done
    if (( found == 0 )); then
      printf '%serror%s unknown skill: %s\n' "$RED" "$RESET" "$name" >&2
      printf '%savailable: %s%s\n' "$DIM" "$(printf '%s, ' ${ALL[@]+"${ALL[@]}"} | sed 's/, $//;s/^$/(none)/')" "$RESET" >&2
      exit 1
    fi
    SELECTED+=("$name")
  done
else
  SELECTED=(${ALL[@]+"${ALL[@]}"})
fi

if (( ${#SELECTED[@]} == 0 )); then
  printf '%sno skills found under skills/%s\n' "$YELLOW" "$RESET"
  exit 0
fi

failures=0
for name in "${SELECTED[@]}"; do
  NOTE=''
  if ! validate "$SKILLS_DIR/$name"; then
    fail "$name" "$REASON"; (( failures++ )); continue
  fi

  case "$MODE" in
    link)   link_skill "$name" || { fail "$name" "$REASON"; (( failures++ )); continue; } ;;
    check)  NOTE="$(collect_files "$name" | wc -l | tr -d ' ') files" ;;
    agents)  NOTE="listed" ;;
    install) install_skill "$name" || { fail "$name" "$REASON"; (( failures++ )); continue; } ;;
    build)  build_skill "$name" || { fail "$name" "$REASON"; (( failures++ )); continue; } ;;
  esac

  ok "$name" "$NOTE"
  if (( ${#DESCRIPTION} < SHORT_DESCRIPTION_LEN )); then
    warn "$name" "description is short — vague descriptions make a skill hard to route to"
  fi
  while IFS= read -r issue; do
    [[ -n "$issue" ]] && warn "$name" "$issue"
  done < <(lint_skill "$name")
done

if [[ "$MODE" == agents ]]; then
  write_agents_md
  printf '%sok%s   %-32s %s%s%s\n' "$GREEN" "$RESET" "AGENTS.md" "$DIM" "$NOTE" "$RESET"
fi

case "$MODE" in
  link)   verb=linked ;;
  check)  verb=checked ;;
  agents)  verb=listed ;;
  install) verb="installed into ${INSTALL_DIR}/.claude/skills" ;;
  *)      verb=built ;;
esac
printf '\n%d/%d %s\n' "$(( ${#SELECTED[@]} - failures ))" "${#SELECTED[@]}" "$verb"
(( failures == 0 ))
