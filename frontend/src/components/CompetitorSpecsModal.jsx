import { X, Warning, Star, ArrowSquareOut } from "@phosphor-icons/react";

export default function CompetitorSpecsModal({
  selectedCompetitor,
  setSelectedCompetitor,
  competitorSpecs,
  isFetchingSpecs,
  competitorSpecsError,
  scrapedData
}) {
  if (!selectedCompetitor) return null;

  return (
    <div className="modal-overlay" onClick={() => setSelectedCompetitor(null)}>
      <div className="modal-container" onClick={e => e.stopPropagation()}>
        <div className="modal-hdr">
          <div>
            <div className="modal-eyebrow">
              {selectedCompetitor.role} Competitor Specs
            </div>
            <h3 className="modal-title">
              {selectedCompetitor.name}
            </h3>
            <div className="modal-meta">
              <span className="modal-meta-item">
                Brand: <strong>{selectedCompetitor.brand || "Unknown"}</strong>
              </span>
              <span className="modal-meta-item">
                Price: <strong className="price-alert">₹{selectedCompetitor.price.toLocaleString()}</strong>
              </span>
            </div>
          </div>
          <button
            onClick={() => setSelectedCompetitor(null)}
            className="modal-close-btn"
          >
            <X size={16} weight="bold" />
          </button>
        </div>
        
        <div className="modal-content custom-scrollbar">
          {isFetchingSpecs ? (
            <div className="modal-loading">
              <div className="spin spin-muted" />
              <div>Pulling live specs...</div>
            </div>
          ) : competitorSpecsError ? (
            <div className="err-box">
              <Warning size={14} weight="fill" className="inline-icon" /> {competitorSpecsError}
            </div>
          ) : competitorSpecs && Object.keys(competitorSpecs).length > 0 ? (
            <div>
              <div className="modal-info-row">
                <span className="modal-info-dot"></span>
                Golden filters only. Everything that matters.
              </div>
              <div className="flex-column-gap-8">
                {Object.entries(competitorSpecs)
                  .filter(([key]) => scrapedData?.filters?.some(f => f.isGolden && f.filterName.toLowerCase() === key.toLowerCase()))
                  .map(([key, value]) => {
                    const isGolden = true;
                    return (
                      <div 
                        key={key} 
                        className="spec-row"
                        data-golden={isGolden ? "true" : "false"}
                      >
                        <div 
                          className="spec-name"
                          data-golden={isGolden ? "true" : "false"}
                        >
                          {key} {isGolden && <Star size={11} weight="fill" className="inline-icon" />}
                        </div>
                        <div className="spec-value">
                          {value}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          ) : (
            <div className="empty">
              No specifications found for this product.
            </div>
          )}
        </div>
        {selectedCompetitor.url && (
          <div className="modal-footer">
            <a 
              href={selectedCompetitor.url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="modal-footer-link"
            >
              View on GeM <ArrowSquareOut size={13} weight="bold" className="inline-icon" />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
