import pytest

from digest.prompts import PromptError, list_prompts, load_prompt, parse_prompt


def test_smoke_prompt_loads_and_renders():
    p = load_prompt("smoke")
    assert p.version_tag == "smoke@v1" and p.model_role == "extractor" and p.output_model == "SmokeOutput"
    assert p.variables == ["name", "number", "text"]
    out = p.render(name="Avery", number=21, text="hello")
    assert "Avery" in out and "21" in out and "{{" not in out
    with pytest.raises(PromptError, match="missing values"):
        p.render(name="Avery")


def test_front_matter_required(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("no front matter")
    with pytest.raises(PromptError):
        parse_prompt(f.read_text(), f)
    f.write_text("---\nname: x\nversion: 1\n---\nbody")
    with pytest.raises(PromptError, match="model_role"):
        parse_prompt(f.read_text(), f)


def test_list_prompts_skips_readme():
    names = [p.name for p in list_prompts()]
    assert "smoke" in names and all(n != "README" for n in names)
