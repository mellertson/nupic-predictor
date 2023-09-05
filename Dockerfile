###############################################################################
# api_server
FROM python:2.7.18-buster

# setup aliases for bash
RUN echo 'alias c="clear"' >> /root/.bashrc
RUN echo 'alias ll="ls -lah"' >> /root/.bashrc
RUN echo 'alias lc="c; ll"' >> /root/.bashrc

# user and group IDs used to run the Docker process.
ARG NUPIC_USER=bamm
ENV NUPIC_USER=${NUPIC_USER:-bamm}
ARG NUPIC_GROUP=bamm
ENV NUPIC_GROUP=${NUPIC_GROUP:-bamm}
ARG NUPIC_USER_ID=9000
ENV NUPIC_USER_ID=${NUPIC_USER_ID:-9000}
ARG NUPIC_GROUP_ID=9000
ENV NUPIC_GROUP_ID=${NUPIC_GROUP_ID:-9000}
RUN groupadd --gid ${NUPIC_GROUP_ID} ${NUPIC_GROUP}
RUN useradd --uid ${NUPIC_USER_ID} \
--gid ${NUPIC_GROUP_ID} \
--no-create-home \
--home-dir /nonexistent \
--shell /usr/sbin/nologin \
${NUPIC_USER}

# Directories for source code and Nupic models, which should be persisted.
# set ENV defaults, which can be overriden at run-time.
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP="nupredictor/nunetwork.py"
ENV FLASK_ENV="development"
ARG PROJECT_ROOT_DIR=/srv/app
ENV PROJECT_ROOT_DIR=${PROJECT_ROOT_DIR:-/srv/app}
ARG NUPIC_MODEL_DIR=${PROJECT_ROOT_DIR}/src/nupredictor/model_input_files
ENV NUPIC_MODEL_DIR=${NUPIC_MODEL_DIR:-${PROJECT_ROOT_DIR}/src/nupredictor/model_input_files}
ARG NUPIC_MODEL_SAVE_DIRECTORY=${PROJECT_ROOT_DIR}/src/nupredictor/saved_models
ENV NUPIC_MODEL_SAVE_DIRECTORY=${NUPIC_MODEL_SAVE_DIRECTORY:-${PROJECT_ROOT_DIR}/src/nupredictor/saved_models}
ENV PYTHONPATH="${PROJECT_ROOT_DIR}/src:/usr/local/lib/python2.7/site-packages"

RUN mkdir -p ${PROJECT_ROOT_DIR}
RUN mkdir -p ${NUPIC_MODEL_DIR}
RUN mkdir -p ${NUPIC_MODEL_SAVE_DIRECTORY}

# install pip and python packages
RUN pip install --no-cache-dir --upgrade pip
COPY ./requirements.txt ${PROJECT_ROOT_DIR}/requirements.txt
RUN pip install --no-cache-dir -r ${PROJECT_ROOT_DIR}/requirements.txt

# copy project code files into Docker image
WORKDIR "${PROJECT_ROOT_DIR}/src"
COPY ./src/nupredictor ${PROJECT_ROOT_DIR}/src/nupredictor
RUN rm -rf ${PROJECT_ROOT_DIR}/src/nupredictor/model_output_files/*
RUN rm -rf ${PROJECT_ROOT_DIR}/src/nupredictor/unit_tests
COPY ./scripts/* ${PROJECT_ROOT_DIR}/scripts/

VOLUME ${NUPIC_MODEL_SAVE_DIRECTORY}

USER ${NUPIC_USER}

# entry point
CMD ["flask", "run", "--host=0.0.0.0"]
ENTRYPOINT ["/srv/app/scripts/docker-entrypoint.sh"]



















