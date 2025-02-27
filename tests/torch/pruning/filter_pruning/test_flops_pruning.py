"""
 Copyright (c) 2022 Intel Corporation
 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
      http://www.apache.org/licenses/LICENSE-2.0
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""
import pytest

from tests.torch.helpers import create_compressed_model_and_algo_for_test
from tests.torch.pruning.helpers import GroupedConvolutionModel
from tests.torch.pruning.helpers import PruningTestModel
from tests.torch.pruning.helpers import PruningTestModelSharedConvs
from tests.torch.pruning.helpers import PruningTestWideModelConcat
from tests.torch.pruning.helpers import PruningTestWideModelEltwise
from tests.torch.pruning.helpers import get_basic_pruning_config


@pytest.mark.parametrize(
    ('pruning_target', 'pruning_flops_target', 'prune_flops_ref', 'pruning_target_ref'),
    [
        (0.3, None, False, 0.3),
        (None, 0.3, True, 0.3),
        (None, None, False, 0.5),
    ]

)
def test_prune_flops_param(pruning_target, pruning_flops_target, prune_flops_ref, pruning_target_ref):
    config = get_basic_pruning_config()
    config['compression']['algorithm'] = 'filter_pruning'
    if pruning_target:
        config['compression']['params']['pruning_target'] = pruning_target
    if pruning_flops_target:
        config['compression']['params']['pruning_flops_target'] = pruning_flops_target
    config['compression']['params']['prune_first_conv'] = True

    model = PruningTestModel()
    _, compression_ctrl = create_compressed_model_and_algo_for_test(model, config)
    assert compression_ctrl.prune_flops is prune_flops_ref
    assert compression_ctrl.scheduler.target_level == pruning_target_ref


def test_both_targets_assert():
    config = get_basic_pruning_config()
    config['compression']['algorithm'] = 'filter_pruning'
    config['compression']['params']['pruning_target'] = 0.3
    config['compression']['params']['pruning_flops_target'] = 0.5

    model = PruningTestModel()
    with pytest.raises(ValueError):
        create_compressed_model_and_algo_for_test(model, config)


@pytest.mark.parametrize(
    ("model", "ref_params"),
    ((PruningTestModel, {"_modules_in_channels": {PruningTestModel.CONV_1_NODE_NAME: 1,
                                                  PruningTestModel.CONV_2_NODE_NAME: 3,
                                                  PruningTestModel.CONV_3_NODE_NAME: 1},
                         "_modules_out_channels": {PruningTestModel.CONV_1_NODE_NAME: 3,
                                                   PruningTestModel.CONV_2_NODE_NAME: 1,
                                                   PruningTestModel.CONV_3_NODE_NAME: 1},
                         "nodes_flops": {PruningTestModel.CONV_1_NODE_NAME: 216,
                                         PruningTestModel.CONV_2_NODE_NAME: 54,
                                         PruningTestModel.CONV_3_NODE_NAME: 2}}),)
)
def test_init_params_for_flops_calculation(model, ref_params):
    config = get_basic_pruning_config()
    config['compression']['algorithm'] = 'filter_pruning'
    config['compression']['params']['pruning_flops_target'] = 0.3
    config['compression']['params']['prune_first_conv'] = True

    model = model()
    _, compression_ctrl = create_compressed_model_and_algo_for_test(model, config)
    for key, value in ref_params.items():
        assert getattr(compression_ctrl, key) == value


@pytest.mark.parametrize(
    ("model", "all_weights", "pruning_flops_target", "ref_full_flops", "ref_current_flops", "ref_sizes"),
    (
        (PruningTestWideModelConcat, False, 0.4, 671154176, 399057920, [328, 656, 656]),
        (PruningTestWideModelEltwise, False, 0.4, 268500992, 160773120, [360, 720, 720]),
        (PruningTestWideModelConcat, True, 0.4, 671154176, 402513920, [380, 647, 648]),
        (PruningTestWideModelEltwise, True, 0.4, 268500992, 161043328, [321, 755, 755]),
        (PruningTestModelSharedConvs, True, 0.4, 461438976, 276594768, [361, 809]),
        (PruningTestModelSharedConvs, False, 0.4, 461438976, 275300352, [384, 768]),
        (GroupedConvolutionModel, False, 0.0, 11243520, 11243520, [])
    )
)
def test_flops_calulation_for_spec_layers(model, all_weights, pruning_flops_target,
                                          ref_full_flops, ref_current_flops, ref_sizes):
    # Need check models with large size of layers because in other case
    # different value of pruning rate give the same final size of model
    config = get_basic_pruning_config([1, 1, 8, 8])
    config['compression']['algorithm'] = 'filter_pruning'
    config['compression']['pruning_init'] = pruning_flops_target
    config['compression']['params']['pruning_flops_target'] = pruning_flops_target
    config['compression']['params']['prune_first_conv'] = True
    config['compression']['params']['all_weights'] = all_weights
    model = model()
    compressed_model, compression_ctrl = create_compressed_model_and_algo_for_test(model, config)

    assert compression_ctrl.full_flops == ref_full_flops
    assert compression_ctrl.current_flops == ref_current_flops

    for i, ref_size in enumerate(ref_sizes):
        node = getattr(compressed_model, f"conv{i+1}")
        op = list(node.pre_ops.values())[0]
        mask = op.operand.binary_filter_pruning_mask
        assert int(sum(mask)) == ref_size
