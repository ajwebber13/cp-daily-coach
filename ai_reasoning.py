"""
ai_reasoning.py
Adds a short, plain-language explanation to a BUY/HOLD/SELL result. The
rules already decided the signal — this just explains why, in a way you
can skim without reading the score breakdown yourself.

Uses Google Gemini's free tier. If GEMINI_API_KEY isn't set, every
function here is a no-op (returns None) so the rest of the coach runs
exactly as before, rules-only.
"""
import config


def _client():
    if not config.AI_REASONING_ENABLED:
        return None
    try:
        from google import genai
        return genai.Client(api_key=config.GEMINI_API_KEY)
    except ImportError:
        print("google-genai package not installed. Run: pip install google-genai")
        return None


SYSTEM_PROMPT = (
    "You explain stock trading signals in plain, simple language — "
    "aim for a 5th-grade reading level. 2-3 sentences maximum. "
    "State facts about the technical setup only. Do not give financial "
    "advice, disclaimers, or hype language. Do not repeat the ticker "
    "or price back verbatim if it's already shown elsewhere — just "
    "explain the reasoning behind the signal."
)


def explain_signal(result: dict) -> str | None:
    """
    result: one of the dicts produced by scorer.evaluate_ticker()
    Returns a short explanation string, or None if reasoning is disabled
    or the API call fails (never raises — a missing explanation should
    never break the scan).
    """
    client = _client()
    if client is None:
        return None

    ticker = result.get("ticker", "")
    signal = result.get("signal", "")

    if signal == "BUY":
        breakdown = result.get("score_breakdown", {})
        checks_passed = [
            name for name, passed in (
                ("trend (price above EMA 200)", breakdown.get("trend")),
                ("crossover (EMA 9 above EMA 20)", breakdown.get("crossover")),
                ("MACD (line above signal)", breakdown.get("macd")),
                ("RSI in the 40-65 zone", breakdown.get("rsi")),
                ("volume above average", breakdown.get("volume")),
            ) if passed
        ]
        user_prompt = (
            f"{ticker} triggered a BUY signal. Checks passed: "
            f"{', '.join(checks_passed) or 'none'} ({breakdown.get('checks_passed', '?')}). "
            f"RSI value: {breakdown.get('rsi_value')}. "
            f"Caution flags: {'; '.join(breakdown.get('flags', [])) or 'none'}. "
            f"Score: {result.get('score')}/100. Entry ${result.get('entry')}, "
            f"stop ${result.get('stop')}, target ${result.get('target')}. "
            f"Explain why this setup scored well."
        )
    elif signal == "HOLD":
        user_prompt = (
            f"{ticker} is currently held, gain so far: {result.get('gain_pct')}%. "
            f"Score: {result.get('score')}/100. Suggested new stop: "
            f"${result.get('suggested_stop')}. Explain briefly why it's still a HOLD."
        )
    elif signal == "SELL":
        user_prompt = (
            f"{ticker} triggered a SELL. Reason: {result.get('reason')}. "
            f"Explain briefly what this means in plain terms."
        )
    else:
        return None

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=user_prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "max_output_tokens": 150,
                "temperature": 0.4,
            },
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI reasoning skipped for {ticker}: {e}")
        return None


def add_reasoning_to_results(results: list) -> list:
    """Attaches a 'reasoning' key to each result dict in place. Safe to call
    even when AI reasoning is disabled — just does nothing in that case."""
    if not config.AI_REASONING_ENABLED:
        return results
    for r in results:
        r["reasoning"] = explain_signal(r)
    return results
