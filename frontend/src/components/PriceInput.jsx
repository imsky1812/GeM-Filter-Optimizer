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
          <div className="card-title">Your Product Price</div>
          <div className="card-desc">
            Enter your price, then continue to choose an analysis.
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
              Find my L1 path →
            </button>
          </div>
        )}
      </div>
      
      {/* Mandatory Filters Section */}
      <details className="mandatory-filters-section mandatory-section">
        <summary className="mandatory-title">
          Advanced: required specs
        </summary>
        <div className="mandatory-desc">
          Select any specific features the buyer absolutely requires. The deep search will start from these filters and find the remaining golden filters needed for L1.
        </div>

        {/* Selected Filters Chips */}
        {mandatoryFilters.length > 0 && (
          <div className="chips-container">
            {mandatoryFilters.map((mf, idx) => (
              <div key={idx} className="chip-item">
                <span className="chip-label">{mf.filterName}:</span>
                <strong className="chip-value">{mf.value}</strong>
                <button
                  onClick={() => setMandatoryFilters(prev => prev.filter((_, i) => i !== idx))}
                  className="chip-close"
                >
                  ✕
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
              {isFilterDropdownOpen ? "▲" : "▼"}
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
                          ▶
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
                                {isSelected && <span className="selected-check">✓</span>}
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
