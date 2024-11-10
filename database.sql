create table if not exists words (
	word_id serial primary key,
	rus_word varchar(70) not null,
	eng_word varchar(70) not null
);

create table if not exists users (
	user_id serial primary key,
	tg_chat_id bigint unique not null
);

create table if not exists user_words (
	user_word_id serial primary key,
	user_id int references users(user_id),
	word_id int references words(word_id),
	is_deleted boolean default false
);

insert into words (rus_word, eng_word) values
('Утро', 'Morning'),
('Нога', 'Leg'),
('Белый', 'White'),
('Привет', 'Hello'),
('Мяч', 'Ball'),
('Дом', 'House'),
('Книга', 'Book'),
('Солнце', 'Sun'),
('Луна', 'Moon'),
('Фиолетовый', 'Violet');
