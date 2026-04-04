"""
通帳画像の前処理モジュール
Pillowを使用して傾き補正・コントラスト強調・ノイズ除去を行い、OCR精度を向上させる
"""

import os
import math
import tempfile
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def preprocess_bank_image(image_path: str) -> str:
    """
    通帳画像を前処理してOCR精度を向上させる。
    処理内容:
      1. 解像度正規化（長辺2400px以上に拡大）
      2. グレースケール変換
      3. コントラスト強調（CLAHE相当）
      4. シャープネス強調
      5. ノイズ除去（メジアンフィルタ相当）
      6. 傾き補正（テキスト行の角度検出）
    Returns:
        前処理済み画像の一時ファイルパス（処理後に呼び出し元で削除すること）
    """
    try:
        img = Image.open(image_path)

        # EXIF情報に基づく自動回転
        img = ImageOps.exif_transpose(img)

        # RGBA/Pモードの場合はRGBに変換
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # 1. 解像度正規化（長辺が2400px未満の場合は拡大）
        w, h = img.size
        long_side = max(w, h)
        if long_side < 2400:
            scale = 2400 / long_side
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        # 2. グレースケール変換
        gray = img.convert('L')

        # 3. コントラスト強調（AutoContrast + Enhancer）
        gray = ImageOps.autocontrast(gray, cutoff=2)
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(1.5)

        # 4. シャープネス強調（文字の輪郭を鮮明に）
        sharp_enhancer = ImageEnhance.Sharpness(gray)
        gray = sharp_enhancer.enhance(2.0)

        # 5. ノイズ除去（軽いメジアンフィルタ）
        gray = gray.filter(ImageFilter.MedianFilter(size=3))

        # 6. 傾き補正（Pillowベースの簡易deskew）
        gray = _deskew(gray)

        # 一時ファイルに保存（JPEG品質95）
        suffix = os.path.splitext(image_path)[1].lower()
        if suffix not in ('.jpg', '.jpeg', '.png'):
            suffix = '.jpg'
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False,
            dir=os.path.dirname(image_path) or tempfile.gettempdir()
        )
        tmp_path = tmp.name
        tmp.close()

        if suffix == '.png':
            gray.save(tmp_path, 'PNG', optimize=True)
        else:
            gray.save(tmp_path, 'JPEG', quality=95, optimize=True)

        print(f'[前処理] 完了: {os.path.basename(image_path)} → {os.path.basename(tmp_path)} ({gray.size[0]}x{gray.size[1]}px)')
        return tmp_path

    except Exception as e:
        print(f'[前処理] エラー（元画像を使用）: {e}')
        return image_path


def _deskew(img: Image.Image) -> Image.Image:
    """
    Pillowを使った簡易傾き補正。
    水平方向の投影ヒストグラムを使って傾き角度を推定し補正する。
    """
    try:
        import struct

        # 二値化（Otsu法の近似）
        threshold = _otsu_threshold(img)
        binary = img.point(lambda p: 255 if p > threshold else 0)

        # 投影ヒストグラムで傾き検出（-10〜+10度の範囲）
        best_angle = 0
        best_score = -1

        for angle_tenth in range(-100, 101, 5):  # -10.0〜10.0度を0.5度刻み
            angle = angle_tenth / 10.0
            rotated = binary.rotate(angle, expand=False, fillcolor=255)
            score = _projection_score(rotated)
            if score > best_score:
                best_score = score
                best_angle = angle

        if abs(best_angle) > 0.3:
            img = img.rotate(best_angle, expand=True, fillcolor=255, resample=Image.BICUBIC)
            print(f'[傾き補正] {best_angle:.1f}度補正')

        return img

    except Exception as e:
        print(f'[傾き補正] スキップ: {e}')
        return img


def _otsu_threshold(img: Image.Image) -> int:
    """Otsu法による最適二値化閾値を計算する"""
    histogram = img.histogram()
    total = sum(histogram)
    if total == 0:
        return 128

    sum_total = sum(i * histogram[i] for i in range(256))
    sum_bg = 0
    weight_bg = 0
    max_variance = 0
    threshold = 128

    for i in range(256):
        weight_bg += histogram[i]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += i * histogram[i]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = i

    return threshold


def _projection_score(binary_img: Image.Image) -> float:
    """
    水平投影ヒストグラムのスコアを計算する。
    テキスト行が水平に揃っているほどスコアが高くなる。
    """
    width, height = binary_img.size
    pixels = binary_img.load()

    row_sums = []
    for y in range(height):
        row_sum = sum(1 for x in range(width) if pixels[x, y] == 0)  # 黒ピクセル数
        row_sums.append(row_sum)

    if not row_sums:
        return 0

    # 分散が大きいほどテキスト行が明確に分離されている
    mean = sum(row_sums) / len(row_sums)
    variance = sum((s - mean) ** 2 for s in row_sums) / len(row_sums)
    return variance
