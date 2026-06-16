from agents.intent_agent import IntentAgent


import asyncio


def test_intent_detection():
    ia = IntentAgent()
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(ia.predict_intent("I want to book an appointment tomorrow"))
    assert isinstance(res, dict)
    assert "intent" in res
