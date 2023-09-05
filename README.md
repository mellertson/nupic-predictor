# Overview

This project implements an HTTP REST API as an interface to build and run
machine learning models.  The REST API is implemented using Flask.  And the 
machine learning models are implemented using Nupic. 

Because, this project's goal is to run machine learning models with real-time 
time series data I used data from Bitmex's Test Net.

**NOTE**

When launched on its on, this Docker container will only bring up a REST API
interface, but will not instatiate nor run any machine learning models.  To
instantiate and run models you must make calls to the REST API.

# Building The Docker Container

Because, Docker Compose is used you can build the container by 
executing the following in a terminal.

```shell script
docker-compose build
```

# Deploying on JONIN (production)

To deploy the Nupic Predictor REST API executing the following on a Docker
Swarm manager node.

```shell script
docker stack deploy -c stack.jonin.yaml --with-registry-auth bamm-nupic-predictor
```

Once launched the REST API should be available at http://localhost:5000.





