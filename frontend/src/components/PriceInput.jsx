import { X, CaretUp, CaretDown, CaretRight, Check, ArrowRight } from "@phosphor-icons/react";

export default function PriceInput({
  sellerPrice,
  setSellerPrice,
  scrapedData,
  minCatPrice,
  priceNum,
  onContinue,
  mandatoryFilters,
  setMandatoryFilters,
  isFilterDropdownOpen,
  setIsFilterDropdownOpen,
  hoveredFilterKey,
  setHoveredFilterKey
}) {
  return (
    <div className="card fade-in fade-in-d1 relative-z-50">
      <div className="card-hdr">
        <div>
          <div className="card-title">Your Price</div>
          <div className="card-desc">
            What are you selling at? We'll find your path to L1.
          </div>
        </div>
      </div>
      <div className="flex-align-center-gap-16">
        <div className="price-wrap">
          <span className="price-sym">₹</span>
          <input
            type="number"
            value={sellerPrice}
            onChange={(e) => setSellerPrice(e.target.value)}
            placeholder={minCatPrice.toLocaleString()}
            id="price-input"
          />
        </div>
        {priceNum > 0 && (
          <div className="flex-gap-12-ml-auto">
            <button className="chain-hunt-trigger" onClick={onContinue}>
              Find my L1 path <ArrowRight size={16} weight="bold" />
            </button>
          </div>
        )}
      </div>
      
      {/* Mandatory Filters Section */}
      <details className="mandatory-filters-section mandatory-section">
        <summary className="mandatory-title">
          Lock in required specs
        </summary>
        <div className="mandatory-desc">
          Specs the buyer won't budge on. We'll build the rest of the path to L1 around them.
        </div>

        {/* Selected Filters Chips */}
        {mandatoryFilters.length > 0 && (
          <div className="chips-container">
            {mandatoryFilters.map((mf, idx) => (
              <div key={idx} className="chip-item" style={{ "--stagger-i": idx }}>
                <span className="chip-label">{mf.filterName}:</span>
                <strong className="chip-value">{mf.value}</strong>
                <button
                  onClick={() => setMandatoryFilters(prev => prev.filter((_, i) => i !== idx))}
                  className="chip-close"
                >
                  <X size={11} weight="bold" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Dropdown UI */}
        <div className="dropdown-wrap">
          <button
            className="btn dropdown-btn"
            onClick={() => setIsFilterDropdownOpen(!isFilterDropdownOpen)}
            data-active={isFilterDropdownOpen ? "true" : "false"}
          >
            + Add Required Spec{" "}
            <span className="dropdown-caret">
              {isFilterDropdownOpen ? <CaretUp size={12} weight="bold" /> : <CaretDown size={12} weight="bold" />}
            </span>
          </button>

          {isFilterDropdownOpen && scrapedData && (
            <div className="dropdown-menu custom-scrollbar">
              {scrapedData.filters
                .filter(f => f.isGolden && f.filterKey !== "mse_applicable")
                .map((filter) => {
                  const isHovered = hoveredFilterKey === filter.filterKey;
                  return (
                    <div key={filter.filterKey} className="dropdown-item-wrapper">
                      <div
                        className="dropdown-item-header"
                        data-active={isHovered ? "true" : "false"}
                        onClick={() => setHoveredFilterKey(isHovered ? null : filter.filterKey)}
                      >
                        <span className="dropdown-item-title">
                          {filter.filterName}
                        </span>
                        <span
                          className="dropdown-chevron-icon"
                          data-active={isHovered ? "true" : "false"}
                        >
                          <CaretRight size={12} weight="bold" />
                        </span>
                      </div>

                      {/* Accordion values list */}
                      {isHovered && (
                        <div className="dropdown-values-list custom-scrollbar">
                          {filter.values.map(val => {
                            const isSelected = mandatoryFilters.some(
                              mf => mf.filterKey === filter.filterKey && mf.value === val
                            );
                            return (
                              <div
                                key={val}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (!isSelected) {
                                    setMandatoryFilters(prev => [...prev, {
                                      filterKey: filter.filterKey,
                                      filterName: filter.filterName,
                                      value: val,
                                      isGolden: true
                                    }]);
                                  }
                                  setIsFilterDropdownOpen(false);
                                  setHoveredFilterKey(null);
                                }}
                                className="dropdown-value-item"
                                data-selected={isSelected ? "true" : "false"}
                              >
                                <span>{val}</span>
                                {isSelected && <span className="selected-check"><Check size={13} weight="bold" /></span>}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
