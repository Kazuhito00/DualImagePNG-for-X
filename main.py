#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import argparse
from typing import Tuple

import numpy as np
from PIL import Image, UnidentifiedImageError


def get_args() -> argparse.Namespace:
    """コマンドライン引数の解析"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--white",
        "-w",
        required=True,
        help="白背景での表示画像",
    )
    parser.add_argument(
        "--black",
        "-b",
        required=True,
        help="黒背景での表示画像",
    )
    parser.add_argument(
        "--out",
        "-o",
        required=True,
        help="出力PNGのパス",
    )
    parser.add_argument(
        "--input-grayscale",
        "-ig",
        action="store_true",
        help="入力をグレースケールとして処理",
    )
    parser.add_argument(
        "--quantize",
        "-q",
        action="store_true",
        help="256色への出力量子化（ファイルサイズ削減）",
    )
    return parser.parse_args()


def load_image(
    path: str,
    as_grayscale: bool,
) -> Image.Image:
    """Pillowによる画像の読み込みと変換"""
    try:
        image = Image.open(path)
        # カラーモードの場合は、後続のYCbCr変換のためにRGBで読み込む
        mode = "L" if as_grayscale else "RGB"
        image = image.convert(mode)
        return image
    except FileNotFoundError:
        print(f"エラー: 入力ファイルが見つかりません: {path}", file=sys.stderr)
        sys.exit(1)
    except UnidentifiedImageError:
        print(
            f"エラー: 指定されたファイルは有効な画像形式ではありません: {path}",
            file=sys.stderr,
        )
        sys.exit(1)


def create_image_from_rgba_array(rgba_array: np.ndarray) -> Image.Image:
    """RGBA配列からPillow画像オブジェクトへの変換"""
    rgb_channels = rgba_array[..., :3]
    alpha_channel = rgba_array[..., 3:4]
    rgb_channels = np.clip(rgb_channels, 0.0, 1.0)
    alpha_channel = np.clip(alpha_channel, 0.0, 1.0)

    output_array = np.concatenate([rgb_channels, alpha_channel], axis=-1)
    image = Image.fromarray((output_array * 255.0 + 0.5).astype(np.uint8), mode="RGBA")
    return image


def calculate_rgba_from_composites(
    white_img_array: np.ndarray, black_img_array: np.ndarray
) -> np.ndarray:
    """
    目的のコンポジットW（白背景）とB（黒背景）からのRGBA（単一アルファ）計算
    """
    white_img_array = np.clip(white_img_array, 0.0, 1.0)
    black_img_array = np.clip(black_img_array, 0.0, 1.0)
    difference = white_img_array - black_img_array
    alpha_channel = 1.0 - np.mean(difference, axis=-1, keepdims=True)

    epsilon = 1e-6
    safe_alpha = np.maximum(alpha_channel, epsilon)
    rgb_channels = black_img_array / safe_alpha
    rgb_channels = np.clip(rgb_channels, 0.0, 1.0)

    transparent_mask = alpha_channel < 1e-3
    if np.any(transparent_mask):
        rgb_channels[transparent_mask.repeat(3, axis=-1)] = white_img_array[
            transparent_mask.repeat(3, axis=-1)
        ]

    return np.concatenate([rgb_channels, alpha_channel], axis=-1)


def calculate_recomposition_error(
    rgba_array: np.ndarray, white_ref_array: np.ndarray, black_ref_array: np.ndarray
) -> Tuple[float, float]:
    """白と黒へのコンポジット時のL2エラー計算（診断用）"""
    rgb_channels = rgba_array[..., :3]
    alpha_channel = rgba_array[..., 3:4]
    comp_white = rgb_channels * alpha_channel + (1.0 - alpha_channel)
    comp_black = rgb_channels * alpha_channel
    error_white = float(np.mean((comp_white - white_ref_array) ** 2))
    error_black = float(np.mean((comp_black - black_ref_array) ** 2))
    return error_white, error_black


def remap_range(
    value: np.ndarray,
    source_min: float,
    source_max: float,
    dest_min: float,
    dest_max: float,
    epsilon: float = 1e-6,
) -> np.ndarray:
    """ある値の区間を別の区間へマッピング"""
    scale = (dest_max - dest_min) / max(source_max - source_min, epsilon)
    return np.clip((value - source_min) * scale + dest_min, dest_min, dest_max)


def convert_ycbcr_to_rgb_numpy(
    y: np.ndarray, cb: np.ndarray, cr: np.ndarray
) -> np.ndarray:
    """YCbCr (0-255) を RGB (0-1) にNumPyで変換"""
    y = y.astype(np.float32)
    cb = cb.astype(np.float32) - 128
    cr = cr.astype(np.float32) - 128

    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb

    rgb = np.stack([r, g, b], axis=-1)
    return np.clip(rgb, 0, 255) / 255.0


def process_images(args: argparse.Namespace) -> np.ndarray:
    """画像処理のメインロジック"""
    # --input-grayscaleフラグに基づいてカラーモードかグレースケールモードかを決定
    is_color_mode = not args.input_grayscale

    # 画像を読み込み
    white_image = load_image(
        args.white,
        as_grayscale=not is_color_mode,
    )
    black_image = load_image(
        args.black,
        as_grayscale=not is_color_mode,
    )

    # 画像サイズのチェック
    if white_image.size != black_image.size:
        print(
            f"エラー: 形状不一致: W{white_image.size} vs B{black_image.size}",
            file=sys.stderr,
        )
        sys.exit(2)

    # --- マージン最適化ループ ---
    # 複数のマージン候補をテストし、再合成誤差が最も小さいものを選択する
    print("最適マージンを探索中...", file=sys.stderr)
    margin_candidates = np.arange(0, 0.45, 0.01)
    min_error = float("inf")
    best_white_array = None
    best_black_array = None

    if is_color_mode:
        # --- カラーモードの処理 ---
        # YCbCr色空間に変換し、輝度(Y)と色差(Cb, Cr)を分離
        white_ycbcr = white_image.convert("YCbCr")
        black_ycbcr = black_image.convert("YCbCr")
        Y_w, Cb_w, Cr_w = white_ycbcr.split()
        Y_b, Cb_b, Cr_b = black_ycbcr.split()

        # 後続の計算のため、各チャンネルをnumpy配列に変換
        y_w_base = np.asarray(Y_w, dtype=np.float32)
        y_b_base = np.asarray(Y_b, dtype=np.float32)
        y_w_min, y_w_max = y_w_base.min(), y_w_base.max()
        y_b_min, y_b_max = y_b_base.min(), y_b_base.max()

        # 色差チャンネルは2つの画像で平均を取り、色情報を維持する
        cb_avg = (
            np.asarray(Cb_w, dtype=np.float32) + np.asarray(Cb_b, dtype=np.float32)
        ) / 2
        cr_avg = (
            np.asarray(Cr_w, dtype=np.float32) + np.asarray(Cr_b, dtype=np.float32)
        ) / 2

        for m in margin_candidates:
            # 輝度チャンネル(Y)のみ、指定の範囲に輝度を再マッピング
            y_w_mapped = remap_range(y_w_base, y_w_min, y_w_max, 127.5 + m * 255, 255)
            y_b_mapped = remap_range(y_b_base, y_b_min, y_b_max, 0, 127.5 - m * 255)

            # 処理した輝度と平均化した色差を結合し、RGBに再変換して評価用配列を生成
            white_eval_arr = convert_ycbcr_to_rgb_numpy(y_w_mapped, cb_avg, cr_avg)
            black_eval_arr = convert_ycbcr_to_rgb_numpy(y_b_mapped, cb_avg, cr_avg)

            # 現在のマージンでRGBAを計算し、誤差を評価
            rgba_eval_arr = calculate_rgba_from_composites(
                white_eval_arr, black_eval_arr
            )
            err_w, err_b = calculate_recomposition_error(
                rgba_eval_arr, white_eval_arr, black_eval_arr
            )
            total_error = err_w + err_b
            print(
                f"  - margin={m:.2f}, err={total_error:.6f} (W:{err_w:.6f}, B:{err_b:.6f})",
                file=sys.stderr,
            )

            # これまでの最小誤差より小さければ、結果を保持
            if total_error < min_error:
                min_error = total_error
                best_margin = m
                best_white_array = white_eval_arr
                best_black_array = black_eval_arr

        print(f"最適マージン: {best_margin:.2f} (カラーモード)", file=sys.stderr)
        white_array, black_array = best_white_array, best_black_array

    else:
        # --- グレースケールモードの処理 ---
        white_array_base = np.asarray(white_image, dtype=np.float32) / 255.0
        black_array_base = np.asarray(black_image, dtype=np.float32) / 255.0
        white_min, white_max = white_array_base.min(), white_array_base.max()
        black_min, black_max = black_array_base.min(), black_array_base.max()

        for m in margin_candidates:
            # グレースケール値を指定の範囲に再マッピング
            white_arr = remap_range(
                white_array_base, white_min, white_max, 0.5 + m, 1.0
            )
            black_arr = remap_range(
                black_array_base, black_min, black_max, 0.0, 0.5 - m
            )
            # RGBA計算のため、3チャンネルに拡張
            white_arr_rgb = np.stack([white_arr] * 3, axis=-1)
            black_arr_rgb = np.stack([black_arr] * 3, axis=-1)

            # 現在のマージンでRGBAを計算し、誤差を評価
            rgba_eval_arr = calculate_rgba_from_composites(white_arr_rgb, black_arr_rgb)
            err_w, err_b = calculate_recomposition_error(
                rgba_eval_arr, white_arr_rgb, black_arr_rgb
            )
            total_error = err_w + err_b
            print(
                f"  - margin={m:.2f}, err={total_error:.6f} (W:{err_w:.6f}, B:{err_b:.6f})",
                file=sys.stderr,
            )

            # これまでの最小誤差より小さければ、結果を保持
            if total_error < min_error:
                min_error = total_error
                best_margin = m
                best_white_array = white_arr_rgb
                best_black_array = black_arr_rgb

        print(
            f"最適マージン: {best_margin:.2f} (グレースケールモード)", file=sys.stderr
        )
        white_array, black_array = best_white_array, best_black_array

    # --- 最終的なRGBA配列の計算 ---
    # 最適化ループで見つかった最良の結果がNoneでないことを確認
    if white_array is None or black_array is None:
        # このエラーは通常発生しないはず
        raise RuntimeError("最適マージンの計算に失敗しました。")

    # 最良のマージンで得られた配列を使用して、最終的なRGBA画像を計算
    rgba_array = calculate_rgba_from_composites(white_array, black_array)

    # 最終結果の品質を診断するために誤差を再計算して表示
    error_white, error_black = calculate_recomposition_error(
        rgba_array, white_array, black_array
    )
    print(f"診断MSE  White={error_white:.6f}  Black={error_black:.6f}", file=sys.stderr)
    return rgba_array


def main() -> None:
    """メイン処理"""

    # --- コマンドライン引数取得 ---
    args = get_args()

    # --- トリック画像生成 ---
    rgba_array = process_images(args)

    # --- 最終的な画像を保存 ---
    output_image = create_image_from_rgba_array(rgba_array)

    if args.quantize:
        output_image = output_image.quantize(colors=256)
    if args.input_grayscale:
        output_image = output_image.convert("LA")

    output_image.save(args.out, compress_level=9)
    print(f"保存完了: {args.out}")


if __name__ == "__main__":
    main()
