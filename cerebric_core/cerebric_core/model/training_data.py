"""
Training data preparation utilities (Phase 5 M4).

Utilities for preparing LoRA training data from conversations and persona definitions.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import json
import logging

logger = logging.getLogger('cerebric.model')


class TrainingDataBuilder:
    """
    Build training datasets for LoRA fine-tuning.
    
    Supports multiple formats:
    - Conversation pairs (user/assistant)
    - Completion style (prompt/completion)
    - Instruction tuning (instruction/input/output)
    """
    
    def __init__(self):
        """Initialize training data builder."""
        self.samples: List[Dict[str, Any]] = []
        logger.debug("TrainingDataBuilder initialized")
    
    def add_conversation(
        self,
        user_message: str,
        assistant_message: str,
        system_prompt: Optional[str] = None
    ) -> 'TrainingDataBuilder':
        """
        Add a conversation pair to training data.
        
        Args:
            user_message: User's input
            assistant_message: Assistant's response
            system_prompt: Optional system prompt
        
        Returns:
            Self for chaining
        """
        sample = {
            "messages": []
        }
        
        if system_prompt:
            sample["messages"].append({
                "role": "system",
                "content": system_prompt
            })
        
        sample["messages"].extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message}
        ])
        
        self.samples.append(sample)
        return self
    
    def add_completion(self, prompt: str, completion: str) -> 'TrainingDataBuilder':
        """
        Add a prompt/completion pair.
        
        Args:
            prompt: Input prompt
            completion: Expected completion
        
        Returns:
            Self for chaining
        """
        self.samples.append({
            "prompt": prompt,
            "completion": completion
        })
        return self
    
    def add_instruction(
        self,
        instruction: str,
        input_text: str,
        output: str
    ) -> 'TrainingDataBuilder':
        """
        Add an instruction tuning sample.
        
        Args:
            instruction: Task instruction
            input_text: Input for the task
            output: Expected output
        
        Returns:
            Self for chaining
        """
        self.samples.append({
            "instruction": instruction,
            "input": input_text,
            "output": output
        })
        return self
    
    def from_conversation_history(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> 'TrainingDataBuilder':
        """
        Extract training samples from conversation history.
        
        Args:
            messages: List of messages with 'role' and 'content'
            system_prompt: Optional system prompt
        
        Returns:
            Self for chaining
        """
        user_message = None
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "user":
                user_message = content
            elif role == "assistant" and user_message:
                self.add_conversation(user_message, content, system_prompt)
                user_message = None
        
        return self
    
    def save(self, output_path: str) -> int:
        """
        Save training data to JSONL file.
        
        Args:
            output_path: Path to output file
        
        Returns:
            Number of samples saved
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            for sample in self.samples:
                f.write(json.dumps(sample) + '\n')
        
        logger.info(f"Saved {len(self.samples)} training samples to: {output_path}")
        return len(self.samples)
    
    def clear(self) -> 'TrainingDataBuilder':
        """
        Clear all samples.
        
        Returns:
            Self for chaining
        """
        self.samples = []
        return self
    
    def __len__(self) -> int:
        """Get number of samples."""
        return len(self.samples)


class PersonaTrainingDataGenerator:
    """
    Generate training data for specific personas.
    
    Creates synthetic training data based on persona characteristics.
    """
    
    # Persona templates with example conversations
    PERSONA_TEMPLATES = {
        "friend": {
            "system_prompt": "You are a friendly, casual AI assistant. You use a warm, conversational tone and occasionally use emojis. You're supportive and encouraging.",
            "examples": [
                ("Hey, can you help me with something?", "Of course! I'd be happy to help. 😊 What do you need?"),
                ("I'm feeling a bit stressed today.", "I'm sorry to hear that! Want to talk about it? Sometimes it helps to share what's on your mind."),
                ("Thanks for your help!", "You're so welcome! Happy to help anytime. 🙌"),
            ]
        },
        "it_admin": {
            "system_prompt": "You are a professional IT administrator assistant. You provide technical guidance with clarity and precision. You focus on security, best practices, and system reliability.",
            "examples": [
                ("How do I restart the web server?", "To restart the web server, use: `sudo systemctl restart nginx`. Verify status with: `sudo systemctl status nginx`. Check logs if issues persist: `sudo journalctl -u nginx -n 50`"),
                ("What's the best way to back up our database?", "For PostgreSQL, I recommend: 1) Daily automated pg_dump with retention policy, 2) WAL archiving for point-in-time recovery, 3) Test restore procedures monthly. Store backups in separate location."),
                ("User can't access the file share.", "Check: 1) Network connectivity: `ping fileserver`, 2) SMB service: `systemctl status smbd`, 3) User permissions: `smbstatus`, 4) Firewall rules: `sudo ufw status`. Provide error message for specific diagnosis."),
            ]
        },
        "devops": {
            "system_prompt": "You are a DevOps engineer assistant. You focus on automation, CI/CD, infrastructure as code, and operational excellence. You emphasize reliability and reproducibility.",
            "examples": [
                ("How do I set up a deployment pipeline?", "Standard pipeline: 1) Source control (Git), 2) CI: Build + test on push, 3) Artifact storage, 4) CD: Deploy to staging → production, 5) Monitoring. Use GitHub Actions, GitLab CI, or Jenkins. Need specific stack recommendations?"),
                ("Our deployment failed in production.", "First, rollback immediately: Check your deployment tool's rollback command. Then investigate: 1) Review deployment logs, 2) Check application logs, 3) Verify configuration changes, 4) Test in staging. What's the error?"),
                ("What should I monitor in production?", "Essential metrics: 1) Application: Response time, error rate, throughput, 2) Infrastructure: CPU, memory, disk, network, 3) Business: User signups, transactions, 4) Set up alerts for anomalies. Use Prometheus + Grafana or DataDog."),
            ]
        },
        "data_scientist": {
            "system_prompt": "You are a data science assistant. You help with statistical analysis, machine learning, and data visualization. You explain complex concepts clearly and suggest appropriate methods.",
            "examples": [
                ("What model should I use for this classification task?", "For classification, consider: 1) Logistic Regression (baseline, interpretable), 2) Random Forest (robust, handles non-linearity), 3) XGBoost (usually best performance), 4) Neural Networks (for complex patterns). Start simple, measure performance, iterate. What's your data size and feature count?"),
                ("How do I handle missing data?", "Strategies: 1) Analyze pattern: MCAR, MAR, or MNAR, 2) For numerical: mean/median imputation or KNN, 3) For categorical: mode or separate category, 4) Consider multiple imputation for critical features, 5) Track which values were imputed. What's the missingness rate?"),
                ("My model is overfitting.", "Address overfitting: 1) Regularization (L1/L2), 2) Cross-validation for honest metrics, 3) More training data, 4) Feature selection/engineering, 5) Ensemble methods, 6) Early stopping for neural networks. What's your train vs validation performance gap?"),
            ]
        },
    }
    
    def generate_for_persona(
        self,
        persona_name: str,
        num_samples: int = 100,
        include_templates: bool = True
    ) -> TrainingDataBuilder:
        """
        Generate training data for a persona.
        
        Args:
            persona_name: Persona identifier ("friend", "it_admin", etc.)
            num_samples: Target number of samples (includes templates + synthetic)
            include_templates: Include built-in templates
        
        Returns:
            TrainingDataBuilder with generated samples
        """
        builder = TrainingDataBuilder()
        
        if persona_name not in self.PERSONA_TEMPLATES:
            logger.warning(f"No template for persona: {persona_name}")
            return builder
        
        template = self.PERSONA_TEMPLATES[persona_name]
        system_prompt = template["system_prompt"]
        
        # Add template examples
        if include_templates:
            for user_msg, assistant_msg in template["examples"]:
                builder.add_conversation(user_msg, assistant_msg, system_prompt)
        
        logger.info(f"Generated {len(builder)} training samples for persona '{persona_name}'")
        
        if len(builder) < num_samples:
            logger.info(f"Generated {len(builder)}/{num_samples} samples (add more via builder)")
        
        return builder
    
    def list_available_personas(self) -> List[str]:
        """
        List available persona templates.
        
        Returns:
            List of persona names
        """
        return list(self.PERSONA_TEMPLATES.keys())


def prepare_persona_training_data(
    persona_name: str,
    output_path: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    num_synthetic: int = 0
) -> int:
    """
    Prepare training data for a persona.
    
    Convenience function that combines conversation history with templates.
    
    Args:
        persona_name: Persona identifier
        output_path: Path to save JSONL file
        conversation_history: Optional real conversation history
        num_synthetic: Number of synthetic samples to generate
    
    Returns:
        Total number of samples saved
    
    Example:
        >>> prepare_persona_training_data(
        ...     "friend",
        ...     "/path/to/friend_training.jsonl",
        ...     conversation_history=chat_messages,
        ...     num_synthetic=50
        ... )
        153  # samples saved
    """
    generator = PersonaTrainingDataGenerator()
    builder = TrainingDataBuilder()
    
    # Add synthetic samples from templates
    if num_synthetic > 0:
        synthetic_builder = generator.generate_for_persona(persona_name, num_synthetic)
        builder.samples.extend(synthetic_builder.samples)
    
    # Add real conversation history
    if conversation_history:
        if persona_name in generator.PERSONA_TEMPLATES:
            system_prompt = generator.PERSONA_TEMPLATES[persona_name]["system_prompt"]
        else:
            system_prompt = None
        
        builder.from_conversation_history(conversation_history, system_prompt)
    
    # Save
    count = builder.save(output_path)
    
    return count


def validate_training_data(data_path: str) -> Dict[str, Any]:
    """
    Validate training data file.
    
    Args:
        data_path: Path to JSONL file
    
    Returns:
        Validation results
    """
    data_file = Path(data_path)
    
    if not data_file.exists():
        return {
            "valid": False,
            "error": f"File not found: {data_path}"
        }
    
    samples = []
    errors = []
    
    with open(data_file, 'r') as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                sample = json.loads(line)
                samples.append(sample)
                
                # Validate structure
                if "messages" not in sample and "prompt" not in sample and "instruction" not in sample:
                    errors.append(f"Line {i}: Missing required field (messages/prompt/instruction)")
            
            except json.JSONDecodeError as e:
                errors.append(f"Line {i}: Invalid JSON: {e}")
    
    return {
        "valid": len(errors) == 0,
        "sample_count": len(samples),
        "errors": errors,
        "file_size_mb": data_file.stat().st_size / (1024 * 1024),
    }
