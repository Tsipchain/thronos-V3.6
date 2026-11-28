from ai_core_chat import APP_PROMPTS


def test_studio_app_profiles_are_registered_and_isolated():
    expected = {
        "thronoslabs-kids",
        "cryptohunters-children",
        "cryptohunters-game",
    }
    assert expected.issubset(APP_PROMPTS)

    kids = APP_PROMPTS["thronoslabs-kids"].lower()
    child = APP_PROMPTS["cryptohunters-children"].lower()
    game = APP_PROMPTS["cryptohunters-game"].lower()

    assert "target age" in kids
    assert "private tenant-scoped" in kids
    assert "never reuse private characters" in kids

    assert "children's adaptation" in child
    assert "do not copy mature" in child
    assert "never invent replacement aliases" in child

    assert "game-production" in game
    assert "children's-adaptation aliases" in game
    assert APP_PROMPTS["cryptohunters-children"] != APP_PROMPTS["cryptohunters-game"]
