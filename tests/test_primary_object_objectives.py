import pytest
import torch

from ai_brain.training.primary_object_objectives import (
    js_consistency,
    supervised_contrastive,
    vicreg,
)


def test_js_identical_zero_symmetric_and_finite_gradients():
    a = torch.randn(6, 9, requires_grad=True)
    b = torch.randn(6, 9, requires_grad=True)
    assert abs(js_consistency(a, a).item()) < 1e-6
    torch.testing.assert_close(js_consistency(a, b), js_consistency(b, a))
    js_consistency(a, b).backward()
    assert torch.isfinite(a.grad).all() and torch.isfinite(b.grad).all()
    with pytest.raises(ValueError):
        js_consistency(
            a, b.masked_fill(torch.ones_like(b, dtype=torch.bool), -torch.inf)
        )


def test_supcon_unknown_excluded_and_two_views_finite():
    a = torch.randn(6, 12, requires_grad=True)
    b = torch.randn(6, 12, requires_grad=True)
    labels = torch.tensor([1, 1, 2, 2, 0, 0])
    loss = supervised_contrastive(a, b, labels, unknown=0)
    changed = b.clone()
    changed[4:] = 100
    torch.testing.assert_close(
        loss, supervised_contrastive(a, changed, labels, unknown=0)
    )
    loss.backward()
    assert torch.isfinite(a.grad).all() and a.grad[4:].count_nonzero() == 0
    assert a.grad[:4].abs().sum() > 0


def test_supcon_separated_class_features_better_than_collapsed():
    features = torch.eye(2).repeat_interleave(2, 0)
    labels = torch.tensor([1, 1, 2, 2])
    assert supervised_contrastive(
        features, features, labels, unknown=0
    ) < supervised_contrastive(
        torch.ones_like(features), torch.ones_like(features), labels, unknown=0
    )
    a = torch.randn(3, 4, requires_grad=True)
    loss = supervised_contrastive(a, a, torch.zeros(3), unknown=0)
    loss.backward()
    assert loss == 0 and a.grad.count_nonzero() == 0


def test_vicreg_collapse_penalty_and_finite_gradient():
    zeros = torch.zeros(8, 4)
    assert vicreg(zeros, zeros) > 20
    a = torch.randn(8, 4, requires_grad=True)
    b = a.detach().clone().requires_grad_(True)
    vicreg(a, b).backward()
    assert torch.isfinite(a.grad).all() and torch.isfinite(b.grad).all()
    with pytest.raises(ValueError):
        vicreg(a[:1], b[:1])
