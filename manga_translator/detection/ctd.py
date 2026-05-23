import os
import shutil
import numpy as np
import einops
from typing import Union, Tuple
import cv2
import torch

from .ctd_utils.basemodel import TextDetBase, TextDetBaseDNN
from .ctd_utils.utils.yolov5_utils import non_max_suppression
from .ctd_utils.utils.db_utils import SegDetectorRepresenter
from .ctd_utils.utils.imgproc_utils import letterbox
from .ctd_utils.textmask import REFINEMASK_INPAINT, refine_mask
from .common import OfflineDetector
from ..utils import Quadrilateral, det_rearrange_forward

def preprocess_img(img, input_size=(1024, 1024), device='cpu', bgr2rgb=True, half=False, to_tensor=True):
    if bgr2rgb:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_in, ratio, (dw, dh) = letterbox(img, new_shape=input_size, auto=False, stride=64)
    if to_tensor:
        img_in = img_in.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
        img_in = np.array([np.ascontiguousarray(img_in)]).astype(np.float32) / 255
        if to_tensor:
            img_in = torch.from_numpy(img_in).to(device)
            if half:
                img_in = img_in.half()
    return img_in, ratio, int(dw), int(dh)

def postprocess_mask(img: Union[torch.Tensor, np.ndarray], thresh=None):
    # img = img.permute(1, 2, 0)
    if isinstance(img, torch.Tensor):
        img = img.squeeze_()
        if img.device != 'cpu':
            img = img.detach().cpu()
        img = img.numpy()
    else:
        img = img.squeeze()
    if thresh is not None:
        img = img > thresh
    img = img * 255
    # if isinstance(img, torch.Tensor):

    return img.astype(np.uint8)

def postprocess_yolo(det, conf_thresh, nms_thresh, resize_ratio, sort_func=None):
    det = non_max_suppression(det, conf_thresh, nms_thresh)[0]
    # bbox = det[..., 0:4]
    if det.device != 'cpu':
        det = det.detach_().cpu().numpy()
    det[..., [0, 2]] = det[..., [0, 2]] * resize_ratio[0]
    det[..., [1, 3]] = det[..., [1, 3]] * resize_ratio[1]
    if sort_func is not None:
        det = sort_func(det)

    blines = det[..., 0:4].astype(np.int32)
    confs = np.round(det[..., 4], 3)
    cls = det[..., 5].astype(np.int32)
    return blines, cls, confs


class ComicTextDetector(OfflineDetector):
    _MODEL_MAPPING = {
        'model-cuda': {
            'url': 'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt',
            'hash': '1f90fa60aeeb1eb82e2ac1167a66bf139a8a61b8780acd351ead55268540cccb',
            'file': '.',
        },
        'model-cpu': {
            'url': 'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx',
            'hash': '1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f',
            'file': '.',
        },
    }

    def __init__(self, *args, **kwargs):
        os.makedirs(self.model_dir, exist_ok=True)
        if os.path.exists('comictextdetector.pt'):
            shutil.move('comictextdetector.pt', self._get_file_path('comictextdetector.pt'))
        if os.path.exists('comictextdetector.pt.onnx'):
            shutil.move('comictextdetector.pt.onnx', self._get_file_path('comictextdetector.pt.onnx'))
        super().__init__(*args, **kwargs)

    async def _load(self, device: str, input_size=1024, half=False, nms_thresh=0.35, conf_thresh=0.4):
        self.device = device
        if self.device == 'cuda' or self.device == 'mps':
            self.model = TextDetBase(self._get_file_path('comictextdetector.pt'), device=self.device, act='leaky')
            self.model.to(self.device)
            self.backend = 'torch'
        else:
            model_path = self._get_file_path('comictextdetector.pt.onnx')
            self.model = cv2.dnn.readNetFromONNX(model_path)
            self.model = TextDetBaseDNN(input_size, model_path)
            self.backend = 'opencv'

        if isinstance(input_size, int):
            input_size = (input_size, input_size)
        self.input_size = input_size
        self.half = half
        self.conf_thresh = conf_thresh
        self.nms_thresh = nms_thresh
        self.seg_rep = SegDetectorRepresenter(thresh=0.3)

    async def _unload(self):
        del self.model

    def det_batch_forward_ctd(self, batch: np.ndarray, device: str) -> Tuple[np.ndarray, np.ndarray]:
        if isinstance(self.model, TextDetBase):
            batch = einops.rearrange(batch.astype(np.float32) / 255., 'n h w c -> n c h w')
            batch = torch.from_numpy(batch).to(device)
            _, mask, lines = self.model(batch)
            mask = mask.detach().cpu().numpy()
            lines = lines.detach().cpu().numpy()
        elif isinstance(self.model, TextDetBaseDNN):
            mask_lst, line_lst = [], []
            for b in batch:
                _, mask, lines = self.model(b)
                if mask.shape[1] == 2:     # some version of opencv spit out reversed result
                    tmp = mask
                    mask = lines
                    lines = tmp
                mask_lst.append(mask)
                line_lst.append(lines)
            lines, mask = np.concatenate(line_lst, 0), np.concatenate(mask_lst, 0)
        else:
            raise NotImplementedError
        return lines, mask

    @torch.no_grad()
    async def _infer(self, image: np.ndarray, detect_size: int, text_threshold: float, box_threshold: float,
                     unclip_ratio: float, verbose: bool = False):

        im_h, im_w = image.shape[:2]
        lines_map, mask = det_rearrange_forward(image, self.det_batch_forward_ctd, self.input_size[0], 4, self.device, verbose)

        # Always run a single-pass YOLO inference for balloon bbox detection
        balloon_bboxes = self._detect_balloons(image)

        if lines_map is None:
            img_in, ratio, dw, dh = preprocess_img(image, input_size=self.input_size, device=self.device, half=self.half, to_tensor=self.backend=='torch')
            blks, mask, lines_map = self.model(img_in)

            if self.backend == 'opencv':
                if mask.shape[1] == 2: # some version of opencv spit out reversed result
                    tmp = mask
                    mask = lines_map
                    lines_map = tmp
            mask = mask.squeeze()
            mask = mask[..., :mask.shape[0]-dh, :mask.shape[1]-dw]
            lines_map = lines_map[..., :lines_map.shape[2]-dh, :lines_map.shape[3]-dw]

        mask = postprocess_mask(mask)
        lines, scores = self.seg_rep(None, lines_map, height=im_h, width=im_w)
        box_thresh = 0.6
        idx = np.where(scores[0] > box_thresh)
        lines, scores = lines[0][idx], scores[0][idx]

        # map output to input img
        mask = cv2.resize(mask, (im_w, im_h), interpolation=cv2.INTER_LINEAR)

        # if lines.size == 0:
        #     lines = []
        # else:
        #     lines = lines.astype(np.int32)

        # YOLO was used for finding bboxes which to order the lines into. This is now solved
        # through the textline merger, which seems to work more reliably.
        # The YOLO language detection seems unnecessary as it could never be as good as
        # using the OCR extracted string directly.
        # Doing it for increasing the textline merge accuracy doesn't really work either,
        # as the merge could be postponed until after the OCR finishes.

        textlines = [Quadrilateral(pts.astype(int), '', score) for pts, score in zip(lines, scores)]
        mask_refined = refine_mask(image, mask, textlines, refine_mode=None)

        # Expand mask within detected balloon regions using flood fill
        if balloon_bboxes is not None and len(balloon_bboxes) > 0:
            mask_refined = self._expand_mask_in_balloons(image, mask_refined, textlines, balloon_bboxes)

        return textlines, mask_refined, None

    @torch.no_grad()
    def _detect_balloons(self, image: np.ndarray) -> np.ndarray:
        """Run a single low-res YOLO pass to detect balloon bounding boxes.

        Returns array of [x1, y1, x2, y2] for class=1 (balloon) detections.
        """
        im_h, im_w = image.shape[:2]
        img_in, ratio, dw, dh = preprocess_img(
            image, input_size=self.input_size, device=self.device,
            half=self.half, to_tensor=self.backend == 'torch'
        )

        if self.backend != 'torch':
            return np.array([])

        blks, _, _ = self.model(img_in)
        resize_ratio = (im_w / (self.input_size[0] - dw), im_h / (self.input_size[1] - dh))
        bboxes, cls, confs = postprocess_yolo(blks, self.conf_thresh, self.nms_thresh, resize_ratio)

        if len(bboxes) == 0:
            return np.array([])

        # class 1 = balloon/speech bubble with clear boundary
        balloon_mask = cls == 1
        return bboxes[balloon_mask]

    def _expand_mask_in_balloons(
        self, image: np.ndarray, mask: np.ndarray,
        textlines: list, balloon_bboxes: np.ndarray
    ) -> np.ndarray:
        """For text regions inside detected balloons, expand mask via flood fill.

        This fills the entire balloon interior (typically white/light background)
        rather than just the text pixels, giving cleaner inpainting results.
        """
        im_h, im_w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image

        for bbox in balloon_bboxes:
            x1, y1, x2, y2 = bbox.astype(int)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(im_w, x2), min(im_h, y2)

            # Check if any textline center falls within this balloon bbox
            has_text = False
            for tl in textlines:
                cx = int(tl.pts[:, 0].mean())
                cy = int(tl.pts[:, 1].mean())
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    has_text = True
                    break

            if not has_text:
                continue

            # Flood fill from the center of the balloon bbox
            roi = gray[y1:y2, x1:x2]
            center_y, center_x = (y2 - y1) // 2, (x2 - x1) // 2

            # Sample the background color at center
            bg_val = int(roi[center_y, center_x])

            # Skip only if center is very dark (likely artwork, not balloon)
            if bg_val < 100:
                continue

            # Create flood fill mask for this balloon region
            fill_mask = np.zeros((y2 - y1 + 2, x2 - x1 + 2), dtype=np.uint8)
            tolerance = 50
            cv2.floodFill(
                roi.copy(), fill_mask,
                (center_x, center_y),
                255,
                loDiff=(tolerance,), upDiff=(tolerance,),
                flags=cv2.FLOODFILL_MASK_ONLY | (255 << 8)
            )

            # Apply the flood fill result to the mask (within bbox bounds)
            balloon_fill = fill_mask[1:-1, 1:-1]
            mask[y1:y2, x1:x2] = cv2.bitwise_or(mask[y1:y2, x1:x2], balloon_fill)

        return mask
