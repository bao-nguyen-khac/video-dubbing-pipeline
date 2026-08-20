// components/VoiceSelector.tsx — Bộ chọn giọng đọc dạng thẻ trực quan (Cards + Filter + Audio Preview)
import { useMemo, useState, useRef, useEffect } from "react";
import { previewVoice, type Voice } from "../api/client";
import { IconCheck, IconClose, IconPause, IconPlay, IconSearch, IconSparkles, IconWave } from "./Icon";
import { PROVIDER_LABELS, inferVoiceTags, voiceKey } from "../lib/labels";
import { useToast } from "../context/ToastContext";

interface VoiceSelectorProps {
  voices: Voice[];
  selectedVoiceKey: string;
  onChange: (voiceKey: string) => void;
  disabled?: boolean;
  label?: string;
}

export default function VoiceSelector({
  voices,
  selectedVoiceKey,
  onChange,
  disabled = false,
  label = "Chọn giọng đọc",
}: VoiceSelectorProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [genderFilter, setGenderFilter] = useState<string>("all");

  const [previewingKey, setPreviewingKey] = useState<string | null>(null);
  const [isPlayingKey, setIsPlayingKey] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const toast = useToast();

  const selectedVoice = useMemo(
    () => voices.find((v) => voiceKey(v) === selectedVoiceKey) ?? (voices.length > 0 ? voices[0] : null),
    [voices, selectedVoiceKey],
  );

  const filteredVoices = useMemo(() => {
    return voices.filter((v) => {
      const { gender } = inferVoiceTags(v.name, v.provider);
      const provName = PROVIDER_LABELS[v.provider] ?? v.provider;
      const matchSearch =
        !search.trim() ||
        v.name.toLowerCase().includes(search.toLowerCase()) ||
        provName.toLowerCase().includes(search.toLowerCase()) ||
        v.voice_id.toLowerCase().includes(search.toLowerCase());

      const matchProvider = providerFilter === "all" || v.provider === providerFilter;
      const matchGender = genderFilter === "all" || gender === genderFilter;

      return matchSearch && matchProvider && matchGender;
    });
  }, [voices, search, providerFilter, genderFilter]);

  const uniqueProviders = useMemo(() => {
    const set = new Set<string>();
    voices.forEach((v) => set.add(v.provider));
    return Array.from(set);
  }, [voices]);

  async function handlePlayPreview(v: Voice, e?: React.MouseEvent) {
    if (e) e.stopPropagation();
    const key = voiceKey(v);

    if (isPlayingKey === key && audioRef.current) {
      audioRef.current.pause();
      setIsPlayingKey(null);
      return;
    }

    setPreviewingKey(key);
    try {
      const blob = await previewVoice(v.provider, v.voice_id);
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      const objectUrl = URL.createObjectURL(blob);
      previewUrlRef.current = objectUrl;

      if (audioRef.current) {
        audioRef.current.src = objectUrl;
        audioRef.current.onended = () => setIsPlayingKey(null);
        await audioRef.current.play();
        setIsPlayingKey(key);
      }
    } catch {
      toast.error("Không nghe thử được giọng này!");
      setIsPlayingKey(null);
    } finally {
      setPreviewingKey(null);
    }
  }

  function handleSelectVoice(v: Voice) {
    onChange(voiceKey(v));
    setModalOpen(false);
  }

  // Dừng phát âm thanh khi unmount
  useEffect(() => {
    const audioEl = audioRef.current;
    return () => {
      if (audioEl) {
        audioEl.pause();
      }
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  const selectedTags = selectedVoice ? inferVoiceTags(selectedVoice.name, selectedVoice.provider) : null;

  return (
    <div className="voice-selector">
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} hidden />

      <div className="voice-selector__header">
        <label className="field__label">{label}</label>
        <span className="field__hint">Hỗ trợ đa dạng nhà cung cấp (Vivibe, Edge-TTS, OmniVoice)</span>
      </div>

      {/* Selected Voice Card */}
      {selectedVoice ? (
        <div className={`voice-card voice-card--selected ${disabled ? "voice-card--disabled" : ""}`}>
          <div className="voice-card__avatar">
            <IconWave size={20} />
          </div>
          <div className="voice-card__body">
            <div className="voice-card__name-row">
              <span className="voice-card__name">{selectedVoice.name}</span>
              <span className="voice-badge voice-badge--provider">
                {PROVIDER_LABELS[selectedVoice.provider] ?? selectedVoice.provider}
              </span>
            </div>
            <div className="voice-card__tags">
              {selectedTags?.gender && <span className="voice-tag">{selectedTags.gender}</span>}
              {selectedTags?.region && <span className="voice-tag">{selectedTags.region}</span>}
              <span className="voice-tag mono">{selectedVoice.voice_id}</span>
            </div>
          </div>

          <div className="voice-card__actions">
            <button
              type="button"
              className={`btn btn--ghost voice-preview-btn ${isPlayingKey === voiceKey(selectedVoice) ? "voice-preview-btn--playing" : ""}`}
              onClick={(e) => handlePlayPreview(selectedVoice, e)}
              disabled={disabled || previewingKey === voiceKey(selectedVoice)}
              title="Nghe thử giọng mẫu"
            >
              {previewingKey === voiceKey(selectedVoice) ? (
                <span className="btn__spinner" />
              ) : isPlayingKey === voiceKey(selectedVoice) ? (
                <>
                  <IconPause size={14} />
                  <span className="voice-wave-anim">
                    <span />
                    <span />
                    <span />
                  </span>
                </>
              ) : (
                <>
                  <IconPlay size={14} />
                  <span>Nghe thử</span>
                </>
              )}
            </button>

            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setModalOpen(true)}
              disabled={disabled || voices.length === 0}
            >
              <IconSparkles size={14} />
              <span>Đổi giọng ({voices.length})</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="voice-card voice-card--empty" onClick={() => !disabled && setModalOpen(true)}>
          <span>{voices.length === 0 ? "Đang nạp danh sách giọng đọc..." : "Chưa chọn giọng đọc — bấm để chọn"}</span>
        </div>
      )}

      {/* Voice Selection Modal */}
      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-content voice-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-header__title">
                <h2>Thư viện giọng đọc AI</h2>
                <span className="field__hint">Chọn giọng đọc phù hợp với phong cách video của bạn</span>
              </div>
              <button
                type="button"
                className="btn btn--subtle modal-close-btn"
                onClick={() => setModalOpen(false)}
                aria-label="Đóng"
              >
                <IconClose size={18} />
              </button>
            </div>

            {/* Filter toolbar */}
            <div className="voice-modal__toolbar">
              <div className="voice-search-wrap">
                <IconSearch size={16} className="voice-search-icon" />
                <input
                  type="text"
                  className="input voice-search-input"
                  placeholder="Tìm theo tên giọng, mã giọng, nhà cung cấp..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  autoFocus
                />
                {search && (
                  <button
                    type="button"
                    className="voice-search-clear"
                    onClick={() => setSearch("")}
                    aria-label="Xoá tìm kiếm"
                  >
                    <IconClose size={14} />
                  </button>
                )}
              </div>

              <div className="voice-filter-chips">
                <div className="filter-group">
                  <span className="filter-group__label">Nhà cung cấp:</span>
                  <button
                    type="button"
                    className={`filter-chip ${providerFilter === "all" ? "filter-chip--active" : ""}`}
                    onClick={() => setProviderFilter("all")}
                  >
                    Tất cả ({voices.length})
                  </button>
                  {uniqueProviders.map((p) => (
                    <button
                      key={p}
                      type="button"
                      className={`filter-chip ${providerFilter === p ? "filter-chip--active" : ""}`}
                      onClick={() => setProviderFilter(p)}
                    >
                      {PROVIDER_LABELS[p] ?? p}
                    </button>
                  ))}
                </div>

                <div className="filter-group">
                  <span className="filter-group__label">Giới tính:</span>
                  <button
                    type="button"
                    className={`filter-chip ${genderFilter === "all" ? "filter-chip--active" : ""}`}
                    onClick={() => setGenderFilter("all")}
                  >
                    Tất cả
                  </button>
                  <button
                    type="button"
                    className={`filter-chip ${genderFilter === "Nữ" ? "filter-chip--active" : ""}`}
                    onClick={() => setGenderFilter("Nữ")}
                  >
                    👩 Nữ
                  </button>
                  <button
                    type="button"
                    className={`filter-chip ${genderFilter === "Nam" ? "filter-chip--active" : ""}`}
                    onClick={() => setGenderFilter("Nam")}
                  >
                    👨 Nam
                  </button>
                </div>
              </div>
            </div>

            {/* Voice Grid */}
            <div className="voice-modal__grid">
              {filteredVoices.length === 0 ? (
                <div className="empty" style={{ padding: "2.5rem" }}>
                  <IconWave size={32} className="empty__icon" />
                  <div className="empty__title">Không tìm thấy giọng đọc phù hợp</div>
                  <p>Hãy thử thay đổi từ khoá tìm kiếm hoặc bộ lọc.</p>
                </div>
              ) : (
                filteredVoices.map((v) => {
                  const key = voiceKey(v);
                  const isSelected = key === (selectedVoice ? voiceKey(selectedVoice) : "");
                  const isPlaying = isPlayingKey === key;
                  const isPreviewing = previewingKey === key;
                  const tags = inferVoiceTags(v.name, v.provider);

                  return (
                    <div
                      key={key}
                      className={`voice-grid-item ${isSelected ? "voice-grid-item--selected" : ""}`}
                      onClick={() => handleSelectVoice(v)}
                    >
                      <div className="voice-grid-item__head">
                        <div className="voice-grid-item__title">
                          <span className="voice-grid-item__name">{v.name}</span>
                          <span className="voice-badge voice-badge--provider">
                            {PROVIDER_LABELS[v.provider] ?? v.provider}
                          </span>
                        </div>
                        {isSelected && (
                          <span className="voice-grid-item__check" title="Đang chọn">
                            <IconCheck size={16} />
                          </span>
                        )}
                      </div>

                      <div className="voice-card__tags">
                        {tags.gender && <span className="voice-tag">{tags.gender}</span>}
                        {tags.region && <span className="voice-tag">{tags.region}</span>}
                        <span className="voice-tag mono">{v.voice_id}</span>
                      </div>

                      <div className="voice-grid-item__footer">
                        <button
                          type="button"
                          className={`btn btn--subtle btn--sm voice-item-preview-btn ${isPlaying ? "voice-preview-btn--playing" : ""}`}
                          onClick={(e) => handlePlayPreview(v, e)}
                          disabled={isPreviewing}
                        >
                          {isPreviewing ? (
                            <span className="btn__spinner" />
                          ) : isPlaying ? (
                            <>
                              <IconPause size={13} />
                              <span className="voice-wave-anim">
                                <span />
                                <span />
                                <span />
                              </span>
                            </>
                          ) : (
                            <>
                              <IconPlay size={13} />
                              <span>Nghe mẫu</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          className={`btn btn--sm ${isSelected ? "btn--primary" : "btn--ghost"}`}
                          onClick={() => handleSelectVoice(v)}
                        >
                          {isSelected ? "Đang chọn" : "Chọn giọng"}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
