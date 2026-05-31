import { FormEvent, useState } from "react";

interface Props {
  onClose: () => void;
  onSubmit: (payload: { keyword: string; category: string | null }) => void;
}

export function CreateModal({ onClose, onSubmit }: Props) {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const kw = keyword.trim();
    if (!kw) return;
    onSubmit({
      keyword: kw,
      category: category.trim() || null,
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h3>새 글 만들기</h3>
        <label>
          키워드
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="예: 강화도 탕수육"
            required
            autoFocus
          />
        </label>
        <label>
          카테고리
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="선택 (예: 맛집·요리)"
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            취소
          </button>
          <button type="submit" className="btn btn-primary">
            생성 시작
          </button>
        </div>
      </form>
    </div>
  );
}
