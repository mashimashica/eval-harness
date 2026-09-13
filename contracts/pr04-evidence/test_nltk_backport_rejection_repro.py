# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Minimal normal-path and hardlink controls rejected by the saved backport.

Run this against the exact patched NLTK source tree recorded in
``nltk-backport-rejection-review.md``.  A usable remediation must pass both
tests.  The saved minimal backport instead errors in the benign roundtrip and
truncates the hardlink victim before reporting a permission failure.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path


class NltkBackportRejectionRepro(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nltk.data
        from nltk import pathsec

        cls._root = Path(tempfile.mkdtemp(prefix="pr04_nltk_rejection_"))
        cls._allowed = cls._root / "allowed"
        cls._outside = cls._root / "outside"
        cls._allowed.mkdir(mode=0o700)
        cls._outside.mkdir(mode=0o700)
        cls._old_paths = list(nltk.data.path)
        cls._old_enforce = pathsec.ENFORCE
        nltk.data.path[:] = [str(cls._allowed)]
        pathsec.ENFORCE = True
        pathsec._ALLOWED_ROOTS_CACHE = None
        pathsec._LAST_DATA_PATHS = None

    @classmethod
    def tearDownClass(cls) -> None:
        import nltk.data
        from nltk import pathsec

        nltk.data.path[:] = cls._old_paths
        pathsec.ENFORCE = cls._old_enforce
        pathsec._ALLOWED_ROOTS_CACHE = None
        pathsec._LAST_DATA_PATHS = None
        shutil.rmtree(cls._root, ignore_errors=True)

    def test_allowed_perceptron_tagger_save_load_roundtrip(self) -> None:
        from nltk.tag.perceptron import PerceptronTagger

        destination = self._allowed / "tagger"
        original = PerceptronTagger(load=False)
        original.model.weights = {"bias": {"NN": 1.0}}
        original.tagdict = {"token": "NN"}
        original.classes = original.model.classes = {"NN"}
        original.save_to_json(lang="pr04", loc=destination)

        loaded = PerceptronTagger(load=False)
        loaded.load_from_json(lang="pr04", loc=destination)
        self.assertEqual(loaded.model.weights, original.model.weights)
        self.assertEqual(loaded.tagdict, original.tagdict)
        self.assertEqual(loaded.classes, original.classes)

    @unittest.skipUnless(os.name == "posix", "hardlink control is POSIX-only")
    def test_rejected_hardlink_write_keeps_outside_victim_intact(self) -> None:
        from nltk.tag.perceptron import AveragedPerceptron

        victim = self._outside / "victim.json"
        original_bytes = b"outside-victim-must-survive"
        victim.write_bytes(original_bytes)
        in_root_link = self._allowed / "hardlink.json"
        os.link(victim, in_root_link)
        self.addCleanup(in_root_link.unlink, missing_ok=True)

        with self.assertRaises(PermissionError):
            AveragedPerceptron({"bias": {"NN": 1.0}}).save(in_root_link)

        self.assertEqual(victim.read_bytes(), original_bytes)
        self.assertEqual(victim.stat().st_nlink, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
