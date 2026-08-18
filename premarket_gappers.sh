#!/usr/bin/env bash
# premarket_gappers.sh
# Scans Yahoo Finance's premarket gainers list, filters for tradeable gappers,
# and looks up a news catalyst for each from Benzinga. Uses the Claude API's
# web_fetch tool to do the fetching + extraction/summarization.
#
# Requires: ANTHROPIC_API_KEY set in the environment, curl, jq.
#
# Usage:
#   ANTHROPIC_API_KEY=sk-ant-... ./premarket_gappers.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set}"

MODEL="claude-opus-5"
API_URL="https://api.anthropic.com/v1/messages"
API_VERSION="2023-06-01"
DATE=$(date +%F)
OUT_FILE="premarket_gappers_${DATE}.json"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

GAP_MIN=5
PRICE_MIN=3
VOL_MIN=50000
TOP_N=10

call_claude() {
  # $1 = prompt, $2 = max_tokens
  curl -sS --max-time 60 "$API_URL" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: $API_VERSION" \
    -H "content-type: application/json" \
    -d "$(jq -n --arg model "$MODEL" --arg prompt "$1" --argjson max_tokens "$2" '{
      model: $model,
      max_tokens: $max_tokens,
      output_config: {effort: "low"},
      tools: [{type: "web_fetch_20260209", name: "web_fetch", max_uses: 1}],
      messages: [{role: "user", content: $prompt}]
    }')"
}

extract_text() {
  jq -r '[.content[]? | select(.type=="text") | .text] | join("")' 2>/dev/null || echo ""
}

# --- Step 1: fetch + parse the gainers table ---
echo "Fetching premarket gainers from Yahoo Finance..." >&2

GAINERS_PROMPT='Fetch https://finance.yahoo.com/markets/stocks/gainers/ and extract every row of the gainers table into a JSON array. For each row include: "symbol" (string), "price" (number), "gap_pct" (number, the percent change shown), "premarket_volume" (number - use the volume figure shown; if a premarket-specific volume is not shown, use the volume field present). Return ONLY a raw JSON array, no markdown fences, no commentary, no explanation.'

GAINERS_RESPONSE=$(call_claude "$GAINERS_PROMPT" 8000)
GAINERS_JSON=$(echo "$GAINERS_RESPONSE" | extract_text | sed -e 's/^```json//' -e 's/^```//' -e 's/```$//')

if ! echo "$GAINERS_JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
  echo "ERROR: could not parse gainers list from Yahoo Finance. Raw API response:" >&2
  echo "$GAINERS_RESPONSE" >&2
  exit 1
fi

# --- Step 2: filter + rank ---
FILTERED=$(echo "$GAINERS_JSON" | jq --argjson gap "$GAP_MIN" --argjson price "$PRICE_MIN" --argjson vol "$VOL_MIN" --argjson n "$TOP_N" '
  [ .[] | select(
      (.gap_pct? // 0) > $gap and
      (.price? // 0) > $price and
      (.premarket_volume? // 0) > $vol
    )
  ]
  | sort_by(-.gap_pct)
  | .[0:$n]
  | to_entries
  | map(.value + {rank: (.key + 1)})
')

COUNT=$(echo "$FILTERED" | jq 'length')
echo "Found $COUNT qualifying gappers after filters." >&2

if [ "$COUNT" -eq 0 ]; then
  jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{scanned_at: $ts, gappers: []}' > "$OUT_FILE"
  echo "Premarket Gappers: 0 names."
  exit 0
fi

# --- Step 3: catalyst lookup per ticker, in parallel ---
echo "Looking up catalysts for top $COUNT tickers..." >&2

TICKERS=$(echo "$FILTERED" | jq -r '.[].symbol')

for TICKER in $TICKERS; do
  (
    PROMPT="What recent news or catalyst is driving ${TICKER} stock today? Return a one-sentence summary, then up to 2 recent headlines verbatim. Just the data - no commentary. Fetch https://www.benzinga.com/quote/${TICKER} for this."
    RESPONSE=$(call_claude "$PROMPT" 1024 2>/dev/null || echo "")
    TEXT=$(echo "$RESPONSE" | extract_text)
    if [ -z "$TEXT" ]; then
      jq -n '{catalyst: null, headlines: []}' > "$TMP_DIR/${TICKER}.json"
    else
      SUMMARY=$(echo "$TEXT" | sed -n '1p' | sed -e 's/^[-*0-9.[:space:]]*//' -e 's/^Summary:[[:space:]]*//I')
      HEADLINES=$(echo "$TEXT" | tail -n +2 | sed -e 's/^[-*0-9.[:space:]]*//' -e 's/^"\(.*\)"$/\1/' | grep -v '^[[:space:]]*$' | head -n 2)
      jq -n --arg s "$SUMMARY" --arg h "$HEADLINES" '{
        catalyst: ($s | if . == "" then null else . end),
        headlines: ($h | split("\n") | map(select(. != "")))
      }' > "$TMP_DIR/${TICKER}.json"
    fi
  ) &
done
wait

# --- Step 4: assemble output ---
GAPPERS_WITH_CATALYSTS=$(echo "$FILTERED" | jq -c '.[]' | while read -r ROW; do
  TICKER=$(echo "$ROW" | jq -r '.symbol')
  CATALYST_FILE="$TMP_DIR/${TICKER}.json"
  if [ -f "$CATALYST_FILE" ]; then
    jq -c -s '.[0] * .[1]' <(echo "$ROW") "$CATALYST_FILE"
  else
    echo "$ROW" | jq -c '. + {catalyst: null, headlines: []}'
  fi
done | jq -s '.')

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
jq -n --arg ts "$TIMESTAMP" --argjson gappers "$GAPPERS_WITH_CATALYSTS" '{scanned_at: $ts, gappers: $gappers}' > "$OUT_FILE"

echo "Saved to $OUT_FILE" >&2

# --- Step 5: one-line summary ---
jq -r '
  "Premarket Gappers: \(.gappers | length) names. Top: " +
  ( [.gappers[0:3][] | "\(.symbol) (\(.gap_pct)%) - \(.catalyst // "no catalyst found")"] | join(", ") )
' "$OUT_FILE"
