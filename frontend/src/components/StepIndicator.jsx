const STEPS = [
  { id: 1, label: "Category" },
  { id: 2, label: "Price" },
  { id: 3, label: "Analysis" },
  { id: 4, label: "Results" },
];

export default function StepIndicator({ currentStep, furthestStep, onStepClick }) {
  return (
    <div className="step-indicator">
      {STEPS.map((step, idx) => {
        const isCurrent = step.id === currentStep;
        const isCompleted = step.id < currentStep || (step.id <= furthestStep && !isCurrent);
        const isClickable = step.id <= furthestStep && !isCurrent;
        const state = isCurrent ? "current" : isCompleted ? "done" : "upcoming";

        return (
          <div className="step-indicator-item" key={step.id}>
            <button
              type="button"
              className="step-indicator-node"
              data-state={state}
              onClick={() => isClickable && onStepClick(step.id)}
              disabled={!isClickable}
            >
              {isCompleted ? "✓" : step.id}
            </button>
            <span className="step-indicator-label" data-state={state}>
              {step.label}
            </span>
            {idx < STEPS.length - 1 && (
              <span className="step-indicator-line" data-state={isCompleted ? "done" : "upcoming"} />
            )}
          </div>
        );
      })}
    </div>
  );
}
