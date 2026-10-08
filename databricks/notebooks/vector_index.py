# Databricks notebook source
from jobs import VectorIndex, VectorIndexConfig

VectorIndex(VectorIndexConfig.from_widgets()).run()
