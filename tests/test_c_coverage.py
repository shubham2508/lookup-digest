"""Orchestrator: coverage matching (OPEN_QUESTIONS #23): exact keys, unique sources, a decider for shared sources."""
from types import SimpleNamespace

from eval.scorer.coverage import Coverage, covered_items, other_sources, sources_for
from eval.scorer.match import about_match


def test_about_match_is_exact_now():
    assert about_match("deal:series-a:cap-table", "DEAL:series-a:cap-table")
    assert not about_match("deal:series-a:cap-table", "deal:series-a:captable"), "no ratio: a near key is not the key"
    assert not about_match("deal:series-a", "deal:series-a:cap-table")


class StubLinker:
    def __init__(self, pick):
        self.pick, self.log, self.asked = pick, [], []

    def match(self, task, questions):
        assert task == "covers_expected"
        self.asked.append(questions)
        self.log.append({"by": "jev"})
        return {q.id: ([self.pick] if self.pick in {o.id for o in q.options} else []) for q in questions}


def _manifest():
    ped = SimpleNamespace(about="family:pediatrician", cites_any=["t-sam-thursday", "event:wren-ped"], notes="overlaps the 2:30 sync", actions=["message_person"])
    care = SimpleNamespace(about="family:daycare-closure", cites_any=["t-sam-thursday", "t-daycare"], notes="daycare closed today", actions=["decide"])
    cap = SimpleNamespace(about="deal:series-a:cap-table", cites_any=["t-marcus-ts"], notes="second slip", actions=["task"])
    rd = SimpleNamespace(items=[ped, care, cap], one_thing=None)
    return SimpleNamespace(run_day=lambda d: rd)


def _view(items, linker):
    v = SimpleNamespace(rendered=items, item_signals=lambda it: [], signals=[], day=30, index=SimpleNamespace(manifest=_manifest()))
    v.coverage = Coverage(linker=linker, tried=True)
    return v


def item(iid, about, sources, what):
    return SimpleNamespace(id=iid, about=about, source_ids=set(sources), what=what, why="", section="urgent", placement="section")


def test_unique_and_shared_sources():
    m = _manifest()
    assert sources_for(m, 30, "family:pediatrician") == {"t-sam-thursday", "event:wren-ped"}
    assert other_sources(m, 30, "family:pediatrician") == {"t-sam-thursday", "t-daycare", "t-marcus-ts"}


def test_unique_source_or_exact_key_needs_no_decider():
    lk = StubLinker(pick=None)
    v = _view([item("i1", "family:wren-visit", ["event:wren-ped"], "Move the sync"),           # unique source
               item("i2", "deal:series-a:cap-table", [], "Send the cap table"),                  # exact key
               item("i3", "deal:series-a:captable", ["t-marcus-ts"], "Send it")], lk)             # near key, but a unique source
    assert covered_items(v, v.index.manifest, "family:pediatrician", None, 30) == {"i1"}
    assert covered_items(v, v.index.manifest, "deal:series-a:cap-table", None, 30) == {"i2", "i3"}
    assert lk.asked == [], "nothing ambiguous, the decider is never asked"


def test_shared_source_goes_to_the_decider_once():
    lk = StubLinker(pick="i5")
    v = _view([item("i4", "family:wren", ["t-sam-thursday"], "Move the 2:30 sync for Wren's visit"),
               item("i5", "family:wren", ["t-sam-thursday"], "Arrange care while daycare is closed")], lk)
    assert covered_items(v, v.index.manifest, "family:daycare-closure", None, 30) == {"i5"}
    assert covered_items(v, v.index.manifest, "family:daycare-closure", None, 30) == {"i5"}, "memoized"
    assert len(lk.asked) == 1 and {o.id for o in lk.asked[0][0].options} == {"i4", "i5"}
    assert v.coverage.log[-1]["by"] == "jev" and v.coverage.log[-1]["matches"] == ["i5"]


def test_no_decider_means_no_credit_but_no_crash():
    v = _view([item("i4", "family:wren", ["t-sam-thursday"], "x")], None)
    assert covered_items(v, v.index.manifest, "family:daycare-closure", None, 30) == set()
    assert v.coverage.log[-1]["by"].startswith("undecided")
