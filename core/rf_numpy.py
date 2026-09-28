"""Small Random Forest in numpy, used only when scikit-learn is missing.

Gini CART trees on bootstrap samples, sqrt(p) random variables per node,
balanced class weights. Slower and simpler than scikit-learn (no
pruning, no parallelism); results will not be identical to sklearn's.
"""

import numpy as np


class _Tree:
    def __init__(self, max_depth, min_leaf, max_features, rng):
        self.max_depth, self.min_leaf = max_depth, min_leaf
        self.max_features, self.rng = max_features, rng

    def fit(self, X, y, w, K):
        feat, thr, left, right, value = [], [], [], [], []

        def new_node():
            feat.append(-1)
            thr.append(0.0)
            left.append(-1)
            right.append(-1)
            value.append(None)
            return len(feat) - 1

        root = new_node()
        stack = [(root, np.arange(len(y)), 0)]
        p = X.shape[1]
        while stack:
            node, idx, depth = stack.pop()
            cw = np.bincount(y[idx], weights=w[idx], minlength=K)
            value[node] = cw / cw.sum() if cw.sum() > 0 else np.ones(K) / K
            if (depth >= self.max_depth or len(idx) < 2 * self.min_leaf or
                    (cw > 0).sum() <= 1):
                continue
            best = (None, None, 0.0)
            parent = 1.0 - ((cw / cw.sum()) ** 2).sum()
            cols = self.rng.choice(p, min(self.max_features, p),
                                   replace=False)
            for j in cols:
                xv = X[idx, j]
                o = np.argsort(xv, kind="mergesort")
                xs, ys, ws = xv[o], y[idx][o], w[idx][o]
                onehot = np.zeros((len(ys), K))
                onehot[np.arange(len(ys)), ys] = ws
                cl = np.cumsum(onehot, axis=0)[:-1]
                tot = cl[-1] + onehot[-1]
                cr = tot - cl
                nl, nr = cl.sum(1), cr.sum(1)
                valid = (xs[1:] != xs[:-1])
                pos = np.arange(1, len(ys))
                valid &= (pos >= self.min_leaf) & (len(ys) - pos >=
                                                   self.min_leaf)
                if not valid.any():
                    continue
                with np.errstate(divide="ignore", invalid="ignore"):
                    gl = 1 - ((cl / nl[:, None]) ** 2).sum(1)
                    gr = 1 - ((cr / nr[:, None]) ** 2).sum(1)
                    g = (nl * gl + nr * gr) / (nl + nr)
                g = np.where(valid, g, np.inf)
                k = int(np.argmin(g))
                gain = parent - g[k]
                if gain > best[2]:
                    best = (j, (xs[k] + xs[k + 1]) / 2, gain)
            if best[0] is None:
                continue
            j, t, _ = best
            m = X[idx, j] <= t
            lnode, rnode = new_node(), new_node()
            feat[node], thr[node] = j, t
            left[node], right[node] = lnode, rnode
            stack.append((lnode, idx[m], depth + 1))
            stack.append((rnode, idx[~m], depth + 1))
        self.feat = np.array(feat)
        self.thr = np.array(thr)
        self.left = np.array(left)
        self.right = np.array(right)
        self.value = np.array(value)
        return self

    def predict_proba(self, X):
        node = np.zeros(len(X), int)
        while True:
            f = self.feat[node]
            inner = f >= 0
            if not inner.any():
                break
            ii = np.nonzero(inner)[0]
            go_left = X[ii, f[ii]] <= self.thr[node[ii]]
            node[ii] = np.where(go_left, self.left[node[ii]],
                                self.right[node[ii]])
        return self.value[node]


class RandomForest:
    def __init__(self, n_estimators=100, max_depth=25, min_samples_leaf=1,
                 random_state=0):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_leaf = max(1, min_samples_leaf)
        self.rng = np.random.default_rng(random_state)

    def fit(self, X, y):
        X = np.asarray(X, np.float64)
        self.classes_, yi = np.unique(np.asarray(y), return_inverse=True)
        K = len(self.classes_)
        counts = np.bincount(yi, minlength=K).astype(float)
        cw = len(yi) / (K * np.maximum(counts, 1))  # balanced weights
        mf = max(1, int(np.sqrt(X.shape[1])))
        self.trees = []
        n = len(yi)
        for _ in range(self.n_estimators):
            b = self.rng.integers(0, n, n)
            t = _Tree(self.max_depth, self.min_leaf, mf, self.rng)
            self.trees.append(t.fit(X[b], yi[b], cw[yi[b]], K))
        return self

    def predict_proba(self, X):
        X = np.asarray(X, np.float64)
        P = np.zeros((len(X), len(self.classes_)))
        for t in self.trees:
            P += t.predict_proba(X)
        return P / len(self.trees)

    def predict(self, X):
        return self.classes_[np.argmax(self.predict_proba(X), axis=1)]
