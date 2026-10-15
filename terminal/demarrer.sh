#!/bin/bash
# Ouvre un shell dans /workspace/hers/<cours> (cours = 1er argument, nom de dossier simple uniquement)
cible=/workspace/hers
case "$1" in
  ""|*/*|.*) ;;
  *) [ -d "/workspace/hers/$1" ] && cible="/workspace/hers/$1" ;;
esac
cd "$cible"
export PS1='\[\e[1;36m\]${PWD#/workspace}\[\e[0m\]\$ '
exec bash --norc -i
