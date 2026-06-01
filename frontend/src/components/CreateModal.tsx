import { FormEvent, useState } from "react";

const IMAGE_SLOT_COUNT = 3;

interface Props {
  onClose: () => void;
  onSubmit: (payload: {
    keyword: string;
    category: string | null;
    slot_prompts: Record<number, string>;
  }) => void;
}

export function CreateModal({ onClose, onSubmit }: Props) {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [slotPrompts, setSlotPrompts] = useState<Record<number, string>>({
    1: "",
    2: "",
    3: "",
  });

  const setSlotPrompt = (slot: number, value: string) => {
    setSlotPrompts((prev) => ({ ...prev, [slot]: value }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const kw = keyword.trim();
    if (!kw) return;
    onSubmit({
      keyword: kw,
      category: category.trim() || null,
      slot_prompts: slotPrompts,
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal modal-wide"
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
            placeholder="예: 삼성전자 ETF"
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
            placeholder="선택 (예: 재테크)"
          />
        </label>
        <fieldset className="slot-prompts-fieldset">
          <legend>이미지 프롬프트 (슬롯 {IMAGE_SLOT_COUNT}개)</legend>
          <p className="field-hint slot-prompts-intro">
            슬롯마다 따로 지정할 수 있습니다. 비우면 키워드·본문 기반 AI
            프롬프트를 사용합니다. 짧게 적으면 Llama 8B가 FLUX용 영문으로
            확장합니다.
          </p>
          {Array.from({ length: IMAGE_SLOT_COUNT }, (_, i) => i + 1).map(
            (slot) => (
              <label key={slot} className="slot-prompt-row">
                #{slot}
                <textarea
                  className="prompt-textarea"
                  value={slotPrompts[slot] ?? ""}
                  onChange={(e) => setSlotPrompt(slot, e.target.value)}
                  placeholder={
                    keyword.trim()
                      ? `비우면 「${keyword.trim()}」 기반 AI 프롬프트`
                      : "비우면 키워드 기반 AI 프롬프트"
                  }
                  rows={2}
                />
              </label>
            ),
          )}
        </fieldset>
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
