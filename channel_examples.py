"""Non-answer channel inputs and public-contract checks; no range solver."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from demo import open_lab
from observatory.archive.storage import ArchiveDatabase
from observatory.archive.repository import DistributionRepository
from observatory.tasks.repository import TaskRepository, TaskConflict
from observatory.tasks.execution import TaskExecutor
from observatory.results.publication import ResultPublisher
from observatory.results.reading import ResultReader, ResultUnavailable

LATENT = [["G", [0, 1]], ["Y", [0, 1]]]


def case(name, counts, latent, channel, event, condition, status, bounds=None):
    return dict(name=name, counts=counts, latent=latent,
                channel=[[F(x) for x in row] for row in channel],
                event=event, condition=condition, status=status, bounds=bounds)


def cases():
    return [
        case("coupled", [3, 2, 0], LATENT,
             [[1, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0]],
             {"Y": 1}, {"G": 1}, "bounded", (F(0), F(3, 5))),
        case("only_g", [1, 1], LATENT,
             [[1, 1, 0, 0], [0, 0, 1, 1]],
             {"Y": 1}, {"G": 1}, "bounded", (F(0), F(1))),
        case("identity", [1, 1, 2, 4], LATENT,
             [[int(i == j) for j in range(4)] for i in range(4)],
             {"Y": 1}, {"G": 1}, "bounded", (F(2, 3), F(2, 3))),
        case("redundant", [1, 1, 2], [["Y", [0, 1]]],
             [[F(1, 2), 0], [F(1, 2), 0], [0, 1]],
             {"Y": 1}, {}, "bounded", (F(1, 2), F(1, 2))),
        case("incompatible", [1, 1], [["Y", [0, 1]]],
             [[1, 1], [0, 0]], {"Y": 1}, {"Y": 1}, "incompatible"),
        case("zero_possible", [1], [["Y", [0, 1]]],
             [[1, 1]], {"Y": 1}, {"Y": 1}, "undefined_condition"),
        case("tiny_positive", [10**30, 1], [["Y", [0, 1]]],
             [[1, 0], [0, 1]], {"Y": 1}, {"Y": 1},
             "bounded", (F(1), F(1))),
        case("opposed", [1, 1], [["Y", [0, 1]]],
             [[1, 0], [0, 1]], {"Y": 0}, {"Y": 1},
             "bounded", (F(0), F(0))),
        case("empty", [1], [], [[1]], {}, {},
             "bounded", (F(1), F(1))),
    ]


def observed(c):
    return [["O", list(range(len(c["counts"])))] ]


def save(ds, tasks, c, task_id=None, source="initial"):
    name = c["name"]
    revision = ds.put_distribution(name, source, observed(c),
                                   [((i,), n) for i, n in enumerate(c["counts"])])
    record = tasks.save_channel_query(task_id or name, name, revision,
                                      c["latent"], c["channel"],
                                      c["event"], c["condition"])
    return revision, record


def pair(x):
    return None if x is None else [x.numerator, x.denominator]


def assert_result(result, c, reader):
    bounds = c["bounds"] or (None, None)
    assert result.status == c["status"], (c["name"], result.status)
    assert (result.lower, result.upper) == bounds, c["name"]
    if c["bounds"]:
        assert type(result.lower) is F and type(result.upper) is F
    assert result.interpretation == "channel_conditional_risk_range"
    data = reader.read_result(result.spec.task_id, structured=True)
    assert data["status"] == c["status"]
    assert (data["lower"], data["upper"]) == tuple(map(pair, bounds))
    assert data["channel"] == [[pair(x) for x in row] for row in c["channel"]]
    assert data["latent_variables"] == c["latent"]
    assert data["event"] == c["event"] and data["condition"] == c["condition"]
    assert data["variables"] == observed(c)
    assert data["source"] == result.spec.source.to_public_record()
    from observatory.results.export import export_result
    assert json.loads(export_result(result)) == data
    return data


class StopBeforeCommit(TaskRepository):
    armed = True

    def mark_completed(self, connection, task_id):
        super().mark_completed(connection, task_id)
        if self.armed:
            raise RuntimeError("channel probe before commit")


class NoCompute(TaskExecutor):
    def _compute(self, *args, **kwargs):
        raise AssertionError("stored channel result must not be recomputed")


def guard_checks(tasks, publisher, result):
    from observatory.results.validation import validate_result

    class View:
        def __init__(self, base, **changes):
            self.base, self.changes = base, changes

        def __getattr__(self, key):
            return self.changes[key] if key in self.changes else getattr(self.base, key)

    for changes in [
        {"spec": tasks.load("only_g").spec},
        {"interpretation": "observational_conditional_probability"},
        {"status": "computable"}, {"lower": 0.0}, {"lower": F(-1)},
        {"lower": F(1), "upper": F(0)},
        {"status": "incompatible", "lower": F(0), "upper": F(1)},
    ]:
        try:
            validate_result(tasks.load(result.spec.task_id), View(result, **changes))
        except ValueError:
            pass
        else:
            raise AssertionError(("guard accepted", changes))


def run(path):
    db, ds, tasks, reader, executor = open_lab(path)
    originals, exports = {}, {}
    try:
        for c in cases():
            revision, record = save(ds, tasks, c)
            result = executor.execute_task(c["name"])
            assert result.spec == record.spec
            assert result.spec.revision == revision
            assert tasks.load(c["name"]).state == "completed"
            originals[c["name"]] = result
            exports[c["name"]] = assert_result(result, c, reader)
        publisher = ResultPublisher(db, tasks)
        guard_checks(tasks, publisher, originals["coupled"])
        c = cases()[0]
        assert save(ds, tasks, c)[1].state == "completed"
        changed = deepcopy(c)
        changed["event"] = {"Y": 0}
        try:
            save(ds, tasks, changed)
        except TaskConflict:
            pass
        else:
            raise AssertionError("changed channel query reused task ID")
        before = db.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        bad = deepcopy(c)
        bad["channel"][0][0] = F(-1)
        try:
            save(ds, tasks, bad, "invalid-channel")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid channel accepted")
        assert db.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
        # Save before changing caller-owned values and before correcting observations.
        c = deepcopy(cases()[0])
        revision, fixed = save(ds, tasks, c, "delayed")
        c["latent"][0][1].reverse()
        c["channel"][0][0] = F(0)
        c["event"]["Y"] = 0
        c["condition"]["G"] = 0
        ds.put_distribution("coupled", "correction", observed(c), [((0,), 1), ((1,), 4), ((2,), 0)])
        assert tasks.load("delayed").spec == fixed.spec
        # Mutating exported copies must not affect persisted results.
        public = originals["coupled"].to_public_record()
        public["channel"][0][0] = F(99)
        public["event"]["Y"] = 0
        copy = reader.read_result("coupled", structured=True)
        copy["lower"][0] = 99
        assert reader.read_result("coupled", structured=True) == exports["coupled"]
    finally:
        db.close()
    db, ds, tasks, reader, executor = open_lab(path)
    try:
        delayed = executor.execute_task("delayed")
        assert delayed.spec == fixed.spec
        assert delayed.spec.revision == revision
        assert_result(delayed, cases()[0], reader)
        for name, original in originals.items():
            assert reader.read_result(name) == original
            assert reader.read_result(name, structured=True) == exports[name]
        publisher = ResultPublisher(db, tasks)
        no_compute = NoCompute(ds, tasks, publisher, reader)
        assert no_compute.execute_task("coupled") == originals["coupled"]
        new = deepcopy(cases()[0])
        new["bounds"] = (F(0), F(1, 5))
        tasks.save_channel_query("after-correction", "coupled", ds.current_revision("coupled"),
                                 new["latent"], new["channel"], new["event"], new["condition"])
        assert_result(executor.execute_task("after-correction"), new, reader)
        stopping = StopBeforeCommit(db, ds)
        save(ds, stopping, cases()[0], "retry")
        pub = ResultPublisher(db, stopping)
        retry_reader = ResultReader(db, stopping)
        retry = TaskExecutor(ds, stopping, pub, retry_reader)
        try:
            retry.execute_task("retry")
        except RuntimeError as exc:
            assert str(exc) == "channel probe before commit"
        else:
            raise AssertionError("injected failure missing")
        assert stopping.load("retry").state == "failed"
        try:
            retry_reader.read_result("retry")
        except ResultUnavailable:
            pass
        else:
            raise AssertionError("partial result published")
        stopping.armed = False
        assert_result(retry.execute_task("retry"), cases()[0], retry_reader)
        actual = reader.read_result("coupled", structured=True)
        print("CHANNEL_SCENARIO " + json.dumps(actual, ensure_ascii=False))
        return actual
    finally:
        db.close()


def fixtures():
    for c in cases():
        public = {**c, "channel": [[pair(x) for x in row] for row in c["channel"]],
                  "bounds": None if c["bounds"] is None else [pair(x) for x in c["bounds"]]}
        print(json.dumps(public, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixtures", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--demo", action="store_true")
    parser.add_argument("--database")
    args = parser.parse_args()
    if args.verify:
        with TemporaryDirectory(prefix="channel-contract-") as directory:
            run(str(Path(directory) / "archive.sqlite3"))
    elif args.demo:
        if not args.database or args.database == ":memory:":
            parser.error("--demo requires a file --database")
        # Each demo uses an explicitly chosen fresh file; never reset a database.
        if Path(args.database).exists():
            parser.error("choose a new database path for this complete scenario")
        run(args.database)
    else:
        fixtures()


if __name__ == "__main__":
    main()
