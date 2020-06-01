import os
from packaging import version

import pytest
import torch

from pytorch_lightning import Trainer, LightningModule
from pytorch_lightning.core.lightning import CHECKPOINT_KEY_MODULE_ARGS
from tests.base import EvalModelTemplate
from omegaconf import OmegaConf
import sys


class OmegaConfModel(EvalModelTemplate):
    def __init__(self, ogc):
        super().__init__()
        self.ogc = ogc
        self.size = ogc.list[0]


def test_class_nesting(tmpdir):

    class MyModule(LightningModule):
        def forward(self):
            return 0

    # make sure PL modules are always nn.Module
    a = MyModule()
    assert isinstance(a, torch.nn.Module)

    def test_outside():
        a = MyModule()
        print(a.module_arguments)

    class A:
        def test(self):
            a = MyModule()
            print(a.module_arguments)

        def test2(self):
            test_outside()

    test_outside()
    A().test2()
    A().test()


@pytest.mark.xfail(version.parse(sys.version_info) < version.parse('3.8'), reason="ogc only for 3.8")
def test_omegaconf(tmpdir):
    conf = OmegaConf.create({"k": "v", "list": [15.4, {"a": "1", "b": "2"}]})
    model = OmegaConfModel(conf)

    # ensure ogc passed values correctly
    assert model.size == 15.4

    trainer = Trainer(default_root_dir=tmpdir, max_epochs=2, overfit_pct=0.5)
    result = trainer.fit(model)

    assert result == 1


class SubClassEvalModel(EvalModelTemplate):
    any_other_loss = torch.nn.CrossEntropyLoss()

    def __init__(self, *args, subclass_arg=1200, **kwargs):
        super().__init__(*args, **kwargs)
        self.subclass_arg = subclass_arg
        self.auto_collect_arguments()


class SubSubClassEvalModel(SubClassEvalModel):
    pass


class AggSubClassEvalModel(SubClassEvalModel):

    def __init__(self, *args, my_loss=torch.nn.CrossEntropyLoss(), **kwargs):
        super().__init__(*args, **kwargs)
        self.my_loss = my_loss
        self.auto_collect_arguments()


@pytest.mark.parametrize("cls", [EvalModelTemplate,
                                 SubClassEvalModel,
                                 SubSubClassEvalModel,
                                 AggSubClassEvalModel])
def test_collect_init_arguments(tmpdir, cls):
    """ Test that the model automatically saves the arguments passed into the constructor """
    extra_args = dict(my_loss=torch.nn.CosineEmbeddingLoss()) if cls is AggSubClassEvalModel else {}

    model = cls(**extra_args)
    assert model.batch_size == 32
    model = cls(batch_size=179, **extra_args)
    assert model.batch_size == 179

    if isinstance(model, SubClassEvalModel):
        assert model.subclass_arg == 1200

    if isinstance(model, AggSubClassEvalModel):
        assert isinstance(model.my_loss, torch.nn.CosineEmbeddingLoss)

    # verify that the checkpoint saved the correct values
    trainer = Trainer(default_root_dir=tmpdir, max_epochs=2, overfit_pct=0.5)
    trainer.fit(model)
    raw_checkpoint_path = os.listdir(trainer.checkpoint_callback.dirpath)
    raw_checkpoint_path = [x for x in raw_checkpoint_path if '.ckpt' in x][0]
    raw_checkpoint_path = os.path.join(trainer.checkpoint_callback.dirpath, raw_checkpoint_path)

    raw_checkpoint = torch.load(raw_checkpoint_path)
    assert CHECKPOINT_KEY_MODULE_ARGS in raw_checkpoint
    assert raw_checkpoint[CHECKPOINT_KEY_MODULE_ARGS]['batch_size'] == 179

    # verify that model loads correctly
    model = cls.load_from_checkpoint(raw_checkpoint_path)
    assert model.batch_size == 179

    if isinstance(model, AggSubClassEvalModel):
        assert isinstance(model.my_loss, torch.nn.CrossEntropyLoss)

    # verify that we can overwrite whatever we want
    model = cls.load_from_checkpoint(raw_checkpoint_path, batch_size=99)
    assert model.batch_size == 99
