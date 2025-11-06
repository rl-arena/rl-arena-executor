# Example Agent Docker Image

This directory contains an example agent Docker image structure.

## Agent Structure

Your agent Docker image should follow this structure:

```
agent-docker-image/
├── Dockerfile
├── requirements.txt
├── agent.py (or main.py)
└── (other dependencies)
```

## Dockerfile Example

```dockerfile
FROM python:3.10-slim

# Install dependencies
COPY requirements.txt /app/
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY agent.py /app/
COPY . /app/

# Agent code will be copied by init container
# No CMD needed - orchestrator will import the module
```

## Agent Code Example

### Option 1: Function-based Agent

```python
# agent.py
import numpy as np

def get_action(observation):
    """
    Get action from observation.
    
    Args:
        observation: Environment observation (numpy array or dict)
        
    Returns:
        Action (int or numpy array depending on environment)
    """
    # Your agent logic here
    # This is a random agent example
    return np.random.randint(0, 4)  # For discrete action space

def reset():
    """Optional: Reset agent state between episodes"""
    pass
```

### Option 2: Class-based Agent

```python
# agent.py
import numpy as np

class Agent:
    """RL Agent"""
    
    def __init__(self):
        """Initialize agent"""
        self.state = None
        
    def get_action(self, observation):
        """
        Get action from observation.
        
        Args:
            observation: Environment observation
            
        Returns:
            Action
        """
        # Your agent logic
        return np.random.randint(0, 4)
        
    def reset(self):
        """Reset agent state"""
        self.state = None
```

## Building and Testing Agent Image

```bash
# Build image
docker build -t my-agent:v1 .

# Test locally
docker run --rm my-agent:v1 python -c "from agent import get_action; import numpy as np; print(get_action(np.zeros(4)))"

# Push to registry (if needed)
docker tag my-agent:v1 registry.example.com/agents/my-agent:v1
docker push registry.example.com/agents/my-agent:v1
```

## Requirements

### Minimum Requirements
- `agent.py` or `main.py` with `get_action()` function or `Agent` class
- Must be importable as a Python module
- Dependencies listed in `requirements.txt`

### Recommended Libraries
```txt
numpy>=1.20.0
gymnasium>=0.28.0
# Add your ML libraries (tensorflow, pytorch, etc.)
```

## Best Practices

1. **Keep images small**: Use slim base images
2. **Pin dependencies**: Specify exact versions in requirements.txt
3. **No network access**: Agents run without network in K8s
4. **Fast initialization**: Minimize startup time
5. **Stateless**: Don't rely on persistent storage between matches
6. **Error handling**: Handle invalid observations gracefully

## Testing Your Agent

```python
# test_agent.py
from agent import get_action
import numpy as np

# Test with dummy observation
obs = np.random.random(4)
action = get_action(obs)
print(f"Action: {action}")

# Test multiple steps
for i in range(10):
    obs = np.random.random(4)
    action = get_action(obs)
    assert isinstance(action, (int, np.ndarray))
    print(f"Step {i}: {action}")
```

## Advanced: Multi-file Agents

```
agent-docker-image/
├── Dockerfile
├── requirements.txt
├── agent.py           # Main entry point
├── model.py           # ML model
├── utils.py           # Helper functions
├── config.json        # Configuration
└── weights/           # Pretrained weights
    └── model.pth
```

```python
# agent.py
from model import MyModel
from utils import preprocess
import json

with open('config.json') as f:
    config = json.load(f)

model = MyModel()
model.load_weights('weights/model.pth')

def get_action(observation):
    processed = preprocess(observation)
    action = model.predict(processed)
    return action
```

## Submitting to Backend

When submitting your agent to the RL Arena backend:

```json
{
  "agent_id": "my_agent_v1",
  "docker_image": "registry.example.com/agents/my-agent:v1",
  "version": "1.0.0",
  "metadata": {
    "description": "DQN agent for Pong",
    "author": "Your Name"
  }
}
```

The backend will include this in the MatchRequest sent to the executor.
