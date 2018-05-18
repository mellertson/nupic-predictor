#!/usr/bin/env bash


for file in $(find ./ -type f); do setfacl -m u:mellertson:rw $file; done
