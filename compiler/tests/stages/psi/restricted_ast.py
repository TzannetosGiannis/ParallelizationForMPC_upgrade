def psi(A: shared[list[int; ?]], D: plaintext[int], B: shared[list[int; ?]], R: plaintext[int], result: shared[list[int; ?]]) -> shared[list[int; ?]]:
    for i: plaintext[int] in range(0, D):
        flag = False
        for j: plaintext[int] in range(0, R):
            if (A[i] == B[j]):
                flag = True
        val = result[i]
        if flag:
            val = A[i]
        result[i] = val
    return result
