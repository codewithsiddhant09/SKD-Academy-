from agents.faq_agent import FAQAgent
import asyncio


def test_faq_agent_no_index():
    fa = FAQAgent()
    loop = asyncio.get_event_loop()
    res = loop.run_until_complete(fa.answer_question("What is Bookly?"))
    # If no vector DB available, should return fallback message
    assert isinstance(res, str)
