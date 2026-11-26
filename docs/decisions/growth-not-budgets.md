# Speed tests assert growth, not a time budget

A test that some work is linear compares the CPU time of four times the input with that of the
input, measured back to back, best of three each (`tests/growth.py`): linear work stays under 8,
quadratic work exceeds it.

**Why.** A fixed budget (under 100 ms) failed whenever other work slowed the machine, such as the
gate's own parallel workers. The ratio of two sizes measured together cancels the load.

**What follows.** `tests/test_growth.py` holds the measure to both sides. A test of a product target
that is a time (a page answered within a budget) keeps its budget, set far above any load.
