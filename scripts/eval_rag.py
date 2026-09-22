"""
Danh gia chat luong RAG pipeline (retrieval + generation) tren mot bo cau hoi
mau co san dap an chuan (ground truth), lay tu chinh du lieu da crawl trong
data/raw/ - khong bia dat thong tin.

Metric (dung Claude lam LLM-judge, cham diem 0-1 cho tung cau hoi):
    - context_precision : trong cac chunk lay ve, bao nhieu % thuc su lien quan
    - context_recall     : cac chunk lay ve co du thong tin de tra loi dung khong
    - faithfulness       : cau tra loi co bam sat context, khong bia dat gi ngoai
    - answer_relevancy   : cau tra loi co dung trong tam cau hoi khong
    - answer_correctness : cau tra loi co dung so voi dap an chuan khong

Cach dung:
    python scripts/eval_rag.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.rag import _anthropic_client, answer_question, retrieve

# Model re, du dung de cham diem (tach biet voi model dung tra loi that trong config.CLAUDE_MODEL)
JUDGE_MODEL = "claude-haiku-4-5-20251001"

# Cau hoi + dap an chuan, doi chieu truc tiep tu van ban goc trong data/raw/.
# Cau cuoi cung (hoc phi) la truong hop KHONG co trong du lieu - dung de kiem
# tra bot co trung thuc tu choi thay vi bia dat hay khong.
EVAL_SET = [
    {
        "question": "Mang điện thoại vào phòng thi bị xử lý kỷ luật như thế nào?",
        "ground_truth": "Sinh viên mang điện thoại vào phòng thi khi không được phép sẽ bị đình chỉ thi.",
    },
    {
        "question": "Sử dụng phần mềm hoặc mạng internet trái phép để hỗ trợ làm bài thi thì bị xử lý ra sao?",
        "ground_truth": "Lần vi phạm thứ nhất bị đình chỉ học 1 kỳ, lần thứ hai bị đuổi học.",
    },
    {
        "question": "Nhờ người khác vào phòng thi thi hộ thì hai bên bị xử lý thế nào?",
        "ground_truth": "Lần vi phạm thứ nhất bị đình chỉ học 1 năm, lần thứ hai bị đuổi học.",
    },
    {
        "question": "Sinh viên bị nâng một mức cảnh báo học tập khi nào?",
        "ground_truth": "Khi số tín chỉ không đạt trong học kỳ lớn hơn 8 tín chỉ.",
    },
    {
        "question": "Sinh viên bị cảnh báo học tập mức 3 hai lần liên tiếp thì bị xử lý thế nào?",
        "ground_truth": "Sinh viên sẽ bị buộc thôi học.",
    },
    {
        "question": "Sinh viên thuộc chương trình đào tạo chuẩn đang bị hạn chế khối lượng học tập được đăng ký tối đa và tối thiểu bao nhiêu tín chỉ mỗi học kỳ?",
        "ground_truth": "Tối đa 14 tín chỉ và tối thiểu 8 tín chỉ cho một học kỳ chính.",
    },
    {
        "question": "Điểm trung bình tích lũy (CPA) được tính như thế nào?",
        "ground_truth": "CPA là trung bình cộng của điểm số các học phần đã tích lũy, quy đổi theo thang điểm 4.",
    },
    {
        "question": "Học phí năm học 2025-2026 của trường là bao nhiêu?",
        "ground_truth": "Không có trong dữ liệu hiện có - đây là câu hỏi kiểm tra bot có trung thực từ chối thay vì bịa đặt hay không.",
    },
]

JUDGE_PROMPT_TEMPLATE = """\
Ban la giam khao danh gia chat luong he thong RAG. Cho diem tu 0.0 den 1.0 \
(so thap phan, cang cao cang tot) cho 5 tieu chi ben duoi, dua tren du lieu sau:

CAU HOI: {question}

DAP AN CHUAN (ground truth): {ground_truth}

CAC DOAN VAN BAN DA TRUY HOI (context, danh so 1..N):
{context_block}

CAU TRA LOI CUA HE THONG: {answer}

Tieu chi cham diem:
1. context_precision: trong so cac doan context tren, ti le doan THUC SU lien \
quan truc tiep den cau hoi (khong phai noise/khong lien quan).
2. context_recall: cac doan context co chua DU thong tin de suy ra dap an \
chuan hay khong (1.0 = du, 0.0 = hoan toan khong co).
3. faithfulness: cau tra loi cua he thong co hoan toan bam sat noi dung trong \
context, KHONG bia dat/suy doan thong tin nao ngoai context hay khong (1.0 = \
hoan toan bam sat hoac tu choi dung khi khong co du lieu, 0.0 = bia dat nhieu).
4. answer_relevancy: cau tra loi co dung trong tam, giai quyet dung cau hoi \
duoc hoi hay khong (khong tinh dung/sai, chi tinh muc do bam sat cau hoi).
5. answer_correctness: cau tra loi co dung noi dung so voi dap an chuan hay \
khong. LUU Y: neu dap an chuan noi "khong co trong du lieu" ma he thong cung \
tra loi trung thuc la khong tim thay/khong the xac nhan (khong bia dat), diem \
nay phai la 1.0 - do la cau tra loi DUNG.

Chi tra ve JSON thuan, khong giai thich them, dung format:
{{"context_precision": 0.0, "context_recall": 0.0, "faithfulness": 0.0, "answer_relevancy": 0.0, "answer_correctness": 0.0}}
"""


def judge(question: str, ground_truth: str, context_block: str, answer: str) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question,
        ground_truth=ground_truth,
        context_block=context_block,
        answer=answer,
    )
    response = _anthropic_client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    # Phong truong hop model tra ve kem markdown code fence
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  [canh bao] khong parse duoc JSON tu judge: {text[:200]}")
        return {}


def run_eval() -> None:
    metric_names = [
        "context_precision",
        "context_recall",
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
    ]
    totals = {m: 0.0 for m in metric_names}
    count = 0

    for i, item in enumerate(EVAL_SET, start=1):
        question = item["question"]
        ground_truth = item["ground_truth"]
        print(f"\n[{i}/{len(EVAL_SET)}] {question}")

        chunks = retrieve(question)
        context_block = "\n\n".join(
            f"[{j}] {c.title}: {c.text[:500]}" for j, c in enumerate(chunks, start=1)
        )

        result = answer_question(question)
        answer = result["answer"]

        scores = judge(question, ground_truth, context_block, answer)
        if not scores:
            continue

        for m in metric_names:
            val = scores.get(m)
            if isinstance(val, (int, float)):
                totals[m] += val
                print(f"  {m}: {val:.2f}")
        count += 1

    if count == 0:
        print("\nKhong co ket qua nao duoc cham diem.")
        return

    print("\n" + "=" * 50)
    print(f"KET QUA TRUNG BINH ({count}/{len(EVAL_SET)} cau hoi cham duoc)")
    print("=" * 50)
    for m in metric_names:
        avg = totals[m] / count
        print(f"{m:22s}: {avg:.2f}")


if __name__ == "__main__":
    run_eval()
