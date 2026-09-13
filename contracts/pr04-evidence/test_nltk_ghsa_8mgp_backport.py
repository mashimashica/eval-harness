# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Acceptance regression for the proposed NLTK 3.10.3 GHSA-8mgp backport.

Run this file against pristine NLTK 3.10.3 and require failure, then against
the exact patched source tree and require success.  These tests exercise every
API named by the advisory and a guarded negative control.  They do not stand in
for the bubblewrap hostile-fixture tests required by PR04.
"""

from __future__ import annotations

import json
import os
import pickle
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _DummySVC:
    def fit(self, _x: object, _y: object) -> "_DummySVC":
        return self


class NltkGhsa8mgpRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nltk.data
        from nltk import pathsec

        cls._root = Path(tempfile.mkdtemp(prefix="pr04_nltk_ghsa_"))
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

    def setUp(self) -> None:
        for child in self._outside.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

    def test_negative_control_rejects_same_outside_path(self) -> None:
        from nltk import pathsec

        with self.assertRaises(PermissionError):
            pathsec.open(self._outside / "negative-control.json", "w")

    def test_averaged_perceptron_save_is_guarded(self) -> None:
        from nltk.tag.perceptron import AveragedPerceptron

        with self.assertRaises(PermissionError):
            AveragedPerceptron({"bias": {"NN": 1.0}}).save(
                self._outside / "weights.json"
            )
        self.assertFalse((self._outside / "weights.json").exists())

    def test_averaged_perceptron_load_is_guarded(self) -> None:
        from nltk.tag.perceptron import AveragedPerceptron

        target = self._outside / "weights.json"
        target.write_text(json.dumps({"bias": {"NN": 1.0}}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            AveragedPerceptron().load(target)

    def test_averaged_perceptron_symlink_write_is_guarded(self) -> None:
        from nltk.tag.perceptron import AveragedPerceptron

        victim = self._outside / "victim.json"
        victim.write_text("untouched", encoding="utf-8")
        link = self._allowed / "link.json"
        link.symlink_to(victim)
        with self.assertRaises(PermissionError):
            AveragedPerceptron({"bias": {"NN": 1.0}}).save(link)
        self.assertEqual(victim.read_text(encoding="utf-8"), "untouched")
        link.unlink()

    def test_perceptron_tagger_save_to_json_is_guarded(self) -> None:
        from nltk.tag.perceptron import PerceptronTagger

        tagger = PerceptronTagger(load=False)
        tagger.model.weights = {"bias": {"NN": 1.0}}
        tagger.classes = {"NN"}
        with self.assertRaises(PermissionError):
            tagger.save_to_json(lang="pr04", loc=self._outside / "tagger")
        self.assertFalse((self._outside / "tagger").exists())

    def test_perceptron_tagger_rejects_path_shaped_filename_component(self) -> None:
        from nltk.tag.perceptron import PerceptronTagger

        tagger = PerceptronTagger(load=False)
        tagger.model.weights = {"bias": {"NN": 1.0}}
        tagger.classes = {"NN"}
        tagger.TAGGER_NAME = "../../outside/escape"
        target = self._allowed / "tagger"
        with self.assertRaises(ValueError):
            tagger.save_to_json(lang="pr04", loc=target)
        self.assertFalse((self._outside / "escape_pr04.weights.json").exists())

    def test_transition_parser_parse_is_guarded(self) -> None:
        from nltk.parse.transitionparser import TransitionParser

        target = self._outside / "model.pickle"
        target.write_bytes(pickle.dumps(None))
        with self.assertRaises(PermissionError):
            TransitionParser("arc-standard").parse([], target)

    def test_transition_parser_train_is_guarded(self) -> None:
        import numpy
        from scipy import sparse

        import nltk.parse.transitionparser as module
        from nltk.parse.transitionparser import TransitionParser

        target = self._outside / "trained.pickle"
        x_train = sparse.csr_matrix([[1.0]])
        y_train = numpy.array([1])

        def write_marker(_model: object, destination: object) -> None:
            destination.write(b"model")

        parser = TransitionParser("arc-standard")
        with (
            mock.patch.object(
                parser, "_create_training_examples_arc_std", return_value=None
            ),
            mock.patch.object(
                module, "load_svmlight_file", return_value=(x_train, y_train)
            ),
            mock.patch.object(module.svm, "SVC", return_value=_DummySVC()),
            mock.patch.object(module.pickle, "dump", side_effect=write_marker),
            self.assertRaises(PermissionError),
        ):
            parser.train([], target, verbose=False)
        self.assertFalse(target.exists())

    def test_save_maxent_params_is_guarded(self) -> None:
        import numpy
        from nltk.classify.maxent import save_maxent_params

        target = self._outside / "maxent"
        with self.assertRaises(PermissionError):
            save_maxent_params(
                numpy.array([1.0]),
                {("a", "b", "c"): 0},
                ["L"],
                {"alwayson": 0},
                tab_dir=str(target),
            )
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
