import { useEffect } from "react";
import { GoalCreateForm } from "./GoalCreateForm";

import "./GoalCreateModal.css";

export const GoalCreateModal = ({
  isOpen,
  onClose,
  onGoalCreated,
}) => {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleGoalCreated = () => {
    onGoalCreated();
    onClose();
  };

  const handleOverlayMouseDown = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="modal-overlay"
      onMouseDown={handleOverlayMouseDown}
      role="dialog"
      aria-modal="true"
      aria-label="Create new goal"
    >
      <div
        className="modal-panel goal-create-modal-panel"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          className="modal-close"
          onClick={onClose}
          aria-label="Close modal"
        >
          ✕
        </button>

        <GoalCreateForm
          onGoalCreated={handleGoalCreated}
        />
      </div>
    </div>
  );
};
