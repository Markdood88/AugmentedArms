"""
model_2x.py — 最終モデル (0.8503, two-band LDA) ※旧 model_v2.py

Winning params (v23 Optuna-B):
  low band:  lc1=0.211, hc1=2.007 Hz, mode='zsd'   (sub-delta, ERP waveform)
  high band: lc2=0.208, hc2=39.045 Hz, mode='log_vd' (gamma, log-scale variance)
  ch=[0,1,2,3,5], ds=10, shrinkage=0.726, solver='lsqr', bl=0

実行すると交差検証精度を表示し、全データで学習したモデルをpickleで保存する。
main.pyからはpredict(file_path)を呼ぶ。
"""

import os, itertools, warnings
import numpy as np
import pandas as pd
import joblib
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from scipy.signal import butter, sosfiltfilt
try:
    from tqdm import tqdm
except ImportError:  # tqdm is only needed for the training entrypoint, not for predict()
    tqdm = lambda x, *a, **k: x

warnings.filterwarnings("ignore")

# ---- paths ----
DATA_FOLDER = "./muto_8ch_seq5"
MODEL_PATH  = "model_2x.pkl"

# ---- winning hyperparams ----
BEST = dict(
    lc1=0.21118197873848127,
    hc1=2.0068449781481585,
    m1="zsd",
    lc2=0.20846979380063277,
    hc2=39.04540871293466,
    m2="log_vd",
    ch=[0, 1, 2, 3, 5],
    ds=10,
    sh=0.726172763864024,
    sol="lsqr",
    bl=0,
    use_car=False,
    avg_mode="mean",
)

SR   = 250
WS   = 250
SEQ  = 5          # repetitions per label used
EC   = [0, 1, 2]  # indices into labels [1,2,3]


# ---- signal processing ----

def _bandpass(sig, lc, hc, fs=250):
    sos = butter(4, [lc, hc], btype="bandpass", fs=fs, output="sos")
    return sosfiltfilt(sos, sig, axis=0)

def _zscore(v):
    return (v - v.mean()) / (v.std() + 1e-10)


def _get_mean_std(path, lc, hc, bl, ch_idx, use_car=False, avg_mode="mean"):
    df   = pd.read_csv(path)
    data = df.values
    stim = np.nan_to_num(data[:, 9], nan=0)

    onsets = np.where(np.diff(stim) != 0)[0] + 1
    onsets = onsets[stim[onsets] != 0][:4 * SEQ]

    all_ch = [f"Ch{i}" for i in range(1, 9)]
    sel    = [all_ch[i] for i in ch_idx] if ch_idx is not None else all_ch
    cidx   = [i for i, c in enumerate(df.columns) if c in sel]

    eeg = data[:, cidx] * -1
    eeg = StandardScaler().fit_transform(eeg)

    if use_car:
        all_cidx = [i for i, c in enumerate(df.columns) if c in all_ch]
        all_eeg  = StandardScaler().fit_transform(data[:, all_cidx] * -1)
        eeg      = eeg - all_eeg.mean(axis=1, keepdims=True)

    eeg = _bandpass(eeg, lc, hc)

    eps_by_lbl = {}
    for o in onsets:
        if o + WS <= eeg.shape[0]:
            lbl = int(stim[o])
            bs  = max(0, o - bl)
            ep  = eeg[o:o+WS] - (eeg[bs:o].mean(axis=0) if o > bs else 0)
            eps_by_lbl.setdefault(lbl, []).append(ep)

    means, stds = {}, {}
    for lbl, eps in eps_by_lbl.items():
        arr = np.array(eps)
        if avg_mode == "mean":
            means[lbl] = arr.mean(axis=0)
            stds[lbl]  = arr.std(axis=0) + 1e-10
        elif avg_mode == "trimmed":
            n_trim = max(1, int(arr.shape[0] * 0.2))
            t = np.sort(arr, axis=0)
            t = t[n_trim:-n_trim] if arr.shape[0] > 2 * n_trim else arr
            means[lbl] = t.mean(axis=0)
            stds[lbl]  = t.std(axis=0) + 1e-10
        elif avg_mode == "weighted":
            w = 1.0 / (arr.var(axis=(1, 2)) + 1e-10)
            w = w / w.sum()
            means[lbl] = np.average(arr, axis=0, weights=w)
            stds[lbl]  = arr.std(axis=0) + 1e-10

    return means, stds


def _band_feat(path, lc, hc, bl, ch_idx, ds, mode, use_car=False, avg_mode="mean"):
    if WS % ds != 0:
        return None
    try:
        means, stds = _get_mean_std(path, lc, hc, bl, ch_idx, use_car, avg_mode)
    except Exception:
        return None
    if not means:
        return None

    n_ch = list(means.values())[0].shape[1]
    df_f = WS // ds
    sel_lbls = [i + 1 for i in EC]
    combs    = list(itertools.combinations(range(len(sel_lbls)), 2))

    def down(M):
        return M.reshape(-1, df_f, n_ch).mean(axis=1).flatten()

    if mode == "zsd":
        return _zscore(np.concatenate([
            down(means[sel_lbls[i]] - means[sel_lbls[j]]) for i, j in combs
        ]))
    elif mode == "vd":
        return _zscore(np.concatenate([
            down(stds[sel_lbls[i]] - stds[sel_lbls[j]]) for i, j in combs
        ]))
    elif mode == "log_vd":
        log_stds = {l: np.log(stds[l] + 1e-10) for l in sel_lbls}
        return _zscore(np.concatenate([
            down(log_stds[sel_lbls[i]] - log_stds[sel_lbls[j]]) for i, j in combs
        ]))
    elif mode == "mvd":
        dm  = [down(means[sel_lbls[i]] - means[sel_lbls[j]]) for i, j in combs]
        ds_ = [down(stds[sel_lbls[i]] - stds[sel_lbls[j]])  for i, j in combs]
        return np.concatenate([_zscore(np.concatenate(dm)), _zscore(np.concatenate(ds_))])
    elif mode == "mvd_log":
        dm       = [down(means[sel_lbls[i]] - means[sel_lbls[j]]) for i, j in combs]
        log_stds = {l: np.log(stds[l] + 1e-10) for l in sel_lbls}
        dls      = [down(log_stds[sel_lbls[i]] - log_stds[sel_lbls[j]]) for i, j in combs]
        return np.concatenate([_zscore(np.concatenate(dm)), _zscore(np.concatenate(dls))])
    return None


def extract_features(path, p=None):
    """Extract two-band features for one CSV file. Returns 1-D feature vector or None."""
    if p is None:
        p = BEST
    f1 = _band_feat(path, p["lc1"], p["hc1"], p["bl"], p["ch"], p["ds"], p["m1"],
                    p["use_car"], p["avg_mode"])
    f2 = _band_feat(path, p["lc2"], p["hc2"], p["bl"], p["ch"], p["ds"], p["m2"],
                    p["use_car"], p["avg_mode"])
    if f1 is None or f2 is None:
        return None
    return np.concatenate([f1, f2])


# ---- public API ----

def predict(file_path):
    """Load saved LDA model and predict label for one recording file."""
    clf = joblib.load(MODEL_PATH)
    feat = extract_features(file_path)
    if feat is None:
        raise ValueError(f"Feature extraction failed for {file_path}")
    return clf.predict(feat.reshape(1, -1))


# ---- training helpers ----

def _load_dataset():
    X, y = [], []
    for root, _, files in os.walk(DATA_FOLDER):
        for fname in sorted(files):
            if not fname.endswith(".csv"):
                continue
            try:
                lbl = int(fname.split("_")[-1].split(".")[0])
            except ValueError:
                continue
            fpath = os.path.join(root, fname)
            feat  = extract_features(fpath)
            if feat is not None:
                X.append(feat)
                y.append(lbl)
    return np.array(X), np.array(y)


def _evaluate(X, y, n=10):
    p = BEST
    sa = []
    for i in range(n):
        clf = LDA(solver=p["sol"], shrinkage=p["sh"])
        sc  = []
        for k in range(3, 10):
            try:
                cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=i)
                for tr, te in cv.split(X, y):
                    Xt, Xe, yt, ye = X[tr], X[te], y[tr], y[te]
                    ul, ct = np.unique(yt, return_counts=True)
                    mc = np.min(ct)
                    np.random.seed(i)
                    idx = np.concatenate([
                        np.random.choice(np.where(yt == l)[0], mc, replace=False)
                        for l in ul
                    ])
                    Xt, yt = Xt[idx], yt[idx]
                    clf.fit(Xt, yt)
                    sc.append(clf.score(Xe, ye))
            except Exception:
                continue
        sa.append(sc or [0.0])
    return float(np.nanmean([np.mean(s) for s in sa]))


if __name__ == "__main__":
    print("Loading dataset from", DATA_FOLDER, "...")
    X, y = _load_dataset()
    print(f"X shape: {X.shape}, labels: {np.unique(y)}")

    print("Running cross-validation (10 random states × k=3,4 StratifiedKFold) ...")
    acc = _evaluate(X, y)
    print(f"Mean accuracy: {acc:.4f}")

    print("Training final model on all data ...")
    p = BEST
    clf = LDA(solver=p["sol"], shrinkage=p["sh"])
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
