import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pymupdf, pytest


def make_pdf(pages=(("Dose 20 mg", 12, (0, 0, 0)),), size=(300, 200), barcode=None, image=None, font="helv"):
    doc = pymupdf.open()
    for text, fs, col in pages:
        pg = doc.new_page(width=size[0], height=size[1])
        pg.insert_text((20, 60), text, fontsize=fs, color=col, fontname=font)
        if image:
            pg.draw_rect(pymupdf.Rect(150, 100, 200, 150), color=None, fill=image)
    return doc.tobytes()


@pytest.fixture
def pdf():
    return make_pdf
