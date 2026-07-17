"""
OCR module for text recognition using RapidOCR.
"""

from dataclasses import dataclass

from rapidocr import RapidOCR, LangCls, LangDet, LangRec, OCRVersion
import numpy as np
import cv2


@dataclass
class Text:
    """
    Data class to hold OCR text output
    """

    box: np.ndarray
    text: str
    score: float


class Image:
    """
    Class for performing OCR on images using RapidOCR.
    """

    def __init__(self, image_path: str):
        """
        Initializes the OCR class with a RapidOCR instance.
        """
        self.engine = RapidOCR(
            params={
                "Det.lang_type": LangDet.CH,
                "Cls.lang_type": LangCls.CH,
                "Rec.lang_type": LangRec.CH,
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Cls.ocr_version": OCRVersion.PPOCRV5,
                "Rec.ocr_version": OCRVersion.PPOCRV6,
            }
        )
        self.image_path = image_path
        self.image = self._load_image()
        self.recognized_texts: list[Text] = []

    def _load_image(self) -> np.ndarray:
        """
        Loads the image from the specified path.
        """
        img = cv2.imread(self.image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found at {self.image_path}")
        return img

    def recognize_text(self):
        ocr_output = self.engine(self.image)

        for box, text, score in zip(
            ocr_output.boxes, ocr_output.txts, ocr_output.scores
        ):
            self.recognized_texts.append(Text(box=box, text=text, score=score))

        return self.recognized_texts

    def preview(self):
        """
        Visualizes the OCR results on top of the image.
        """
        preview_img = self.image.copy()

        # Draw bounding boxes and text on the image
        for text in self.recognized_texts:
            box = text.box.astype(int)
            cv2.polylines(
                preview_img, [box], isClosed=True, color=(0, 255, 0), thickness=2
            )
            cv2.putText(
                preview_img,
                f"{text.text} ({text.score:.2f})",
                (box[0][0], box[0][1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

        # Create window
        cv2.namedWindow("OCR Preview", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("OCR Preview", 1200, 800)
        cv2.imshow("OCR Preview", preview_img)

        cv2.waitKey(0)
        cv2.destroyAllWindows()
