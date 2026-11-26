"""Hand-worked git logs in the format the module reads: `%H%x1f%P%x1f%ct%x1f%B%x1e`."""


def record(commit: str, parents: str, at: int, message: str) -> str:
    """One record as `git log` prints it: the message ends in a newline, then the separator."""
    return f"{commit}\x1f{parents}\x1f{at}\x1f{message}\n\x1e\n"


# A history worked by hand, newest first:
# - c0 starts main at 1000;
# - ticket/cf-12 commits a1 (1100) and a2 (1200), merged as #7 by m1 at 1500;
# - tickets/cf-13 files a ticket, merged as #8 by m2 at 1600;
# - process/clean-slate commits b1 (1300), merges main into itself as b2 (1650), commits b3
#   (1700), and is merged as #9 by m3 at 1800.
SHIPPED = "".join(
    [
        record("m3", "m2 b3", 1800, "Merge pull request #9 from o/process/clean-slate"),
        record("b3", "b2", 1700, "More"),
        record("b2", "b1 m2", 1650, "Merge main into the branch"),
        record("m2", "m1 t1", 1600, "Merge pull request #8 from o/tickets/cf-13"),
        record("t1", "m1", 1550, "File CF-13"),
        record("m1", "c0 a2", 1500, "Merge pull request #7 from o/ticket/cf-12"),
        record("b1", "c0", 1300, "Start the slate"),
        record("a2", "a1", 1200, "CF-12: finish"),
        record("a1", "c0", 1100, "CF-12: start"),
        record("c0", "", 1000, "Start"),
    ]
)

# - #7 (ticket/cf-12, commit a1, which only mentions #7 and #8) merged by m1;
# - #8 (fix/thing, commit b1, which says it reverts `step#12`, no pull request) merged by m2;
# - #9 merged by m3 brings r1, whose message says it reverts #8;
# - #10 (ticket/cf-13) merged by m4 brings d2, which says it reverts #10: its own change;
# - #11 merged by m5 brings e1, whose message names #7 the way GitHub's revert does;
# - #12 merged by m6 brings f1, which only says #9 never reverted cleanly.
REVERTS = "".join(
    [
        record("m6", "m5 f1", 1600, "Merge pull request #12 from o/ticket/cf-14"),
        record("f1", "m5", 1550, "CF-14: note\n\nThe unreverts #9 note stays."),
        record("m5", "m4 e1", 1500, "Merge pull request #11 from o/revert-7"),
        record("e1", "m4", 1450, 'Revert "CF-12: work"\n\nReverts o/sample#7'),
        record("m4", "m3 d2", 1400, "Merge pull request #10 from o/ticket/cf-13"),
        record("d2", "d1", 1380, "CF-13: back out\n\nThis reverts #10."),
        record("d1", "m3", 1350, "CF-13: try"),
        record("m3", "m2 r1", 1300, "Merge pull request #9 from o/revert/thing\n\nRevert the fix"),
        record(
            "r1",
            "m2",
            1250,
            "Revert the fix\n\nIt broke the suite. This reverts #8; the checks\nfail closed again.",
        ),
        record("m2", "m1 b1", 1200, "Merge pull request #8 from o/fix/thing"),
        record("b1", "m1", 1150, "Fix thing\n\nIt reverts step#12 of the plan."),
        record("m1", "c0 a1", 1100, "Merge pull request #7 from o/ticket/cf-12"),
        record("a1", "c0", 1050, "CF-12: work\n\nSee #7 and #8."),
        record("c0", "", 1000, "Start"),
    ]
)
