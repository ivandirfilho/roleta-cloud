"""DIR4 (sentido-fase): reconciliação de fase por SHIFT dos últimos resultados.

Conta quantos giros REAIS entraram comparando a leitura nova com o histórico —
a munição (allNumbers) que o cliente já envia e o servidor ignorava.
"""

from state.phase import reconcile_shift


def test_normal_one_new():
    prev = [10, 20, 30, 5]
    new = [7, 10, 20, 30, 5]
    assert reconcile_shift(prev, new) == (1, True)


def test_duplicate_no_new():
    assert reconcile_shift([10, 20, 30], [10, 20, 30]) == (0, True)


def test_gap_two_new():
    prev = [30, 5, 12]
    new = [7, 22, 30, 5, 12]
    assert reconcile_shift(prev, new) == (2, True)


def test_gap_three_new():
    prev = [1, 2, 3, 4]
    new = [9, 8, 7, 1, 2, 3, 4]
    assert reconcile_shift(prev, new) == (3, True)


def test_no_overlap_means_resync():
    k, matched = reconcile_shift([1, 2, 3], [10, 11, 12])
    assert matched is False


def test_empty_new():
    assert reconcile_shift([1, 2], []) == (0, True)


def test_empty_prev_first_read():
    assert reconcile_shift([], [5, 6, 7]) == (1, True)


def test_repeated_numbers_subsequence():
    # números repetidos: alinhamento posicional, não de conjunto
    assert reconcile_shift([0, 5, 0, 5], [9, 0, 5, 0, 5]) == (1, True)
